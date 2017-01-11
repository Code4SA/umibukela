from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.views.generic.base import TemplateView
from wkhtmltopdf.utils import wkhtmltopdf
from wkhtmltopdf.views import PDFResponse
import analysis
import pandas
import requests
import settings
import unicodedata

from .models import (
    CycleResultSet,
    Partner,
    Site,
    Survey,
)


def home(request):
    return render(request, 'index.html', {
        'active_tab': 'home',
    })


def about(request):
    return render(request, 'about.html', {
        'active_tab': 'about',
    })


def learn(request):
    return render(request, 'learn.html', {
        'active_tab': 'learn',
    })


def resources(request):
    return render(request, 'resources.html', {
        'active_tab': 'resources',
    })


def sites(request):
    sites = Site.objects.all().prefetch_related('province', 'sector')

    return render(request, 'sites.html', {
        'active_tab': 'sites',
        'sites': sites,
    })


def site(request, site_slug):
    site = get_object_or_404(Site, slug=site_slug)
    return render(request, 'site_detail.html', {
        'active_tab': 'sites',
        'site': site,
    })


def site_result(request, site_slug, result_id):
    result_set = get_object_or_404(
        CycleResultSet,
        id=result_id,
        site__slug__exact=site_slug
    )
    site_responses = [s.answers for s in result_set.submissions.all()]
    if site_responses:
        df = pandas.DataFrame(site_responses)
        form = result_set.survey.form
        site_totals = analysis.count_submissions(df)
        site_results = analysis.count_options(df, form['children'])
        site_results = analysis.calc_q_percents(site_results)
        prev_result_set = result_set.get_previous()
        if prev_result_set:
            prev_responses = [s.answers for s in prev_result_set.submissions.all()]
            if prev_responses:
                site_totals = analysis.count_submissions(
                    pandas.DataFrame(site_responses + prev_responses))
                prev_df = pandas.DataFrame(prev_responses)
                prev_form = prev_result_set.survey.form
                prev_results = analysis.count_options(prev_df, prev_form['children'])
                prev_results = analysis.calc_q_percents(prev_results)
            else:
                prev_results = None
        else:
            prev_results = None
        analysis.combine_curr_hist(site_results, prev_results)
    else:
        site_totals = {'male': 0, 'female': 0, 'total': 0}
        site_results = None

    return render(request, 'site_result_detail.html', {
        'active_tab': 'sites',
        'result_set': result_set,
        'results': {
            'questions_dict': site_results,
            'totals': site_totals,
        }
    })


def partners(request):
    partners = Partner.objects.all()
    return render(request, 'partners.html', {
        'active_tab': 'partners',
        'partners': partners,
    })


def partner(request, partner_slug):
    partner = get_object_or_404(Partner, slug=partner_slug)
    return render(request, 'partner_detail.html', {
        'active_tab': 'partners',
        'partner': partner,
    })


def kobo_forms(request):
    if not is_kobo_authed(request):
        return start_kobo_oauth(request)
    else:
        headers = {
            'Authorization': "Bearer %s" % request.session.get('kobo_access_token'),
        }
        r = requests.get("https://kc.kobotoolbox.org/api/v1/forms",
                         headers=headers)
        r.raise_for_status()
        available_surveys = r.json()
        surveys = []
        for survey_json in available_surveys:
            survey = {
                'title': survey_json['title'],
                'num_of_submissions': survey_json['num_of_submissions'],
            }
            if 'formid' in survey_json:
                survey['kobo_survey_id'] = survey_json['formid']
                r = requests.get("https://kc.kobotoolbox.org/api/v1/forms/%d/form.json" % survey_json['formid'],
                                 headers=headers)
                r.raise_for_status()
                form = r.json()
                fields = form.get('children', [])
                facility_fields = [c for c in fields if c.get('name', None) in ('facility', 'site')]
                if facility_fields:
                    survey['facilities'] = facility_fields[0]['children']
            surveys.append(survey)

        return render(request, 'survey_sources.html', {
            'kobo_access_token_expiry': request.session.get('kobo_access_token_expiry'),
            'forms': surveys,
        })


class SurveySitePreviewPDF(TemplateView):
    def get(self, request, *args, **kwargs):
        if is_kobo_authed(request):
            kobo_survey_id = kwargs.get('kobo_survey_id')
            site_name = kwargs.get('site_name')
            headers = {
                'Authorization': "Bearer %s" % request.session.get('kobo_access_token'),
            }
            r = requests.get("https://kc.kobotoolbox.org/api/v1/forms/%s/form.json" % kobo_survey_id, headers=headers)
            r.raise_for_status()
            form = r.json()
            for q in form['children']:
                for option in q.get('children', []):
                    if option['name'] == site_name:
                        site_label = option['label']

            # render as pdf
            url = request.build_absolute_uri('preview.pdf')
            pdf = wkhtmltopdf(url, zoom=0.7)
            filename = '%s - %s.pdf' % (form['title'], site_label)
            filename = unicodedata.normalize('NFKD', filename).encode('ascii','ignore')
            return PDFResponse(pdf, filename=filename)
        else:
            return start_kobo_oauth(request)


class SurveySitePreview(TemplateView):
    template_name = 'survey_preview.html'

    def dispatch(self, *args, **kwargs):
        request = self.request
        if is_kobo_authed(request):
            return super(SurveySitePreview, self).dispatch(*args, **kwargs)
        else:
            return start_kobo_oauth(request)

    def get_context_data(self, *args, **kwargs):
        request = self.request
        kobo_survey_id = kwargs.get('kobo_survey_id')
        site_name = kwargs.get('site_name')
        headers = {
            'Authorization': "Bearer %s" % request.session.get('kobo_access_token'),
        }
        r = requests.get("https://kc.kobotoolbox.org/api/v1/forms/%s/form.json" % kobo_survey_id, headers=headers)
        r.raise_for_status()
        form = r.json()
        map_question_names(form)
        r = requests.get("https://kc.kobotoolbox.org/api/v1/data/%s" % kobo_survey_id, headers=headers)
        r.raise_for_status()
        submissions = r.json()
        site_responses = [s for s in submissions if s.get('facility', s.get('site', None)) == site_name]
        site_responses = field_per_SATA_option(form, site_responses)

        if site_responses:
            df = pandas.DataFrame(site_responses)
            site_totals = analysis.count_submissions(df)
            site_results = analysis.count_options(df, form['children'])
            site_results = analysis.calc_q_percents(site_results)
            prev_results = None
            analysis.combine_curr_hist(site_results, prev_results)
        else:
            site_totals = {'male': 0, 'female': 0, 'total': 0}
            site_results = None

        for q in form['children']:
            for option in q.get('children', []):
                if option['name'] == site_name:
                    site_label = option['label']
        return {
            'site_name': site_label,
            'form_title': form['title'],
            'results': {
                'questions_dict': site_results,
                'totals': site_totals,
            }
        }


def map_question_names(form):
    names = {
        'Please_select_your_gender': 'gender'
    }
    for q in form.get('children', []):
        if q.get('name', None) in names:
            q['name'] = names[q['name']]


def field_per_SATA_option(form, submissions):
    SATAs = [q for q in form['children'] if q['type'] == 'select all that apply']
    for SATA in SATAs:
        vals = [o['name'] for o in SATA['children']]
        submissions = map(
            lambda x: set_select_all_that_apply_fields(x, SATA['name'], vals),
            submissions
        )
    return submissions


def set_select_all_that_apply_fields(dict, q_key, possible_vals):
    for val in possible_vals:
        dict['/'.join([q_key, val])] = 'False'
    for val in dict[q_key].split(','):
        dict['/'.join([q_key, val])] = 'True'
    del dict[q_key]
    return dict


def is_kobo_authed(request):
    kobo_expiry = request.session.get('kobo_access_token_expiry', None)
    return kobo_expiry and kobo_expiry > datetime.utcnow().isoformat()


def start_kobo_oauth(request):
    state = request.path
    return redirect("https://kc.kobotoolbox.org/o/authorize?client_id=%s&response_type=code&scope=read&state=%s" % (settings.KOBO_CLIENT_ID, state))


def kobo_oauth_return(request):
    state = request.GET.get('state')
    code = request.GET.get('code')
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'http://localhost:8000/admin/kobo-oauth'
    }
    r = requests.post("https://kc.kobotoolbox.org/o/token/",
                     params=payload,
                     auth=(settings.KOBO_CLIENT_ID, settings.KOBO_CLIENT_SECRET))
    r.raise_for_status()
    request.session['kobo_access_token'] = r.json()['access_token']
    expiry_datetime = datetime.utcnow() + timedelta(seconds=r.json()['expires_in'])
    request.session['kobo_access_token_expiry'] = expiry_datetime.isoformat()
    return redirect(state)
