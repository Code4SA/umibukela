from datetime import datetime, timedelta
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from itertools import groupby
import analysis
import pandas
import requests
import settings

from forms import CRSFromKoboForm

from .models import (
    CycleResultSet,
    KoboRefreshToken,
    Partner,
    Site,
    Survey,
    SurveyKoboProject,
    Submission,
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
        site__slug__exact=site_slug,
        published=True
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


def survey_from_kobo(request):
    if not is_kobo_authed(request):
        return start_kobo_oauth(request)
    else:
        headers = {
            'Authorization': "Bearer %s" % request.session.get('kobo_access_token'),
        }
        if request.method == 'POST':
            form_id = request.POST['form_id']
            r = requests.get("https://kc.kobotoolbox.org/api/v1/forms/%s/form.json" % form_id,
                             headers=headers)
            r.raise_for_status()
            form = r.json()
            survey = Survey(name=form['title'], form=r.text)
            survey.save()
            survey_kobo_project = SurveyKoboProject(survey=survey, form_id=form_id)
            survey_kobo_project.save()
            return redirect('/admin/umibukela/survey/%d' % survey.id)
        else:
            r = requests.get("https://kc.kobotoolbox.org/api/v1/forms",
                             headers=headers)
            r.raise_for_status()
            available_surveys = r.json()
            return render(request, 'survey_from_kobo.html', {
                'forms': available_surveys,
            })


def survey_kobo_submissions(request, survey_id):
    if not is_kobo_authed(request):
        return start_kobo_oauth(request)
    else:
        headers = {
            'Authorization': "Bearer %s" % request.session.get('kobo_access_token'),
        }
        survey = get_object_or_404(Survey, id=survey_id)
        form_id = survey.surveykoboproject.form_id
        r = requests.get("https://kc.kobotoolbox.org/api/v1/data/%s" % form_id, headers=headers)
        r.raise_for_status()
        submissions = r.json()
        facilities = []
        facility_labels = {}
        for q in survey.form['children']:
            if q['name'] == 'facility':
                for o in q['children']:
                    facility_labels[o['name']] = o['label']
        facility_key = lambda r: r['facility']
        facility_sorted = sorted(submissions, key=facility_key, reverse=True)
        facilities = []
        for facility_name, facility_group in groupby(facility_sorted, facility_key):
            facilities.append({
                'name': facility_name,
                'label': facility_labels[facility_name],
                'count': len(list(facility_group)),
            })
        crs_form = CRSFromKoboForm(facilities=facilities)
        if request.method == 'POST':
            num_facilities = request.POST['num_facilities']
            facility_crs = {}
            for i in xrange(int(num_facilities)):
                facility_name = request.POST['facility_%d' % i]
                crs_id = int(request.POST['crs_%d' % i])
                facility_crs[facility_name] = CycleResultSet.objects.get(pk=crs_id)
            submissions = field_per_SATA_option(survey.form, submissions)
            for answers in submissions:
                facility_name = answers['facility']
                submission = Submission(
                    answers=answers,
                    cycle_result_set=facility_crs[facility_name]
                )
                submission.save()
            return HttpResponseRedirect('/admin/umibukela/cycleresultset', status=303)
        return render(request, 'survey_kobo_submissions.html', {
            'survey': survey,
            'facilities': facilities,
            'crs_form': crs_form,
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
                survey['kobo_form_id'] = survey_json['formid']
                r = requests.get("https://kc.kobotoolbox.org/api/v1/forms/%d/form.json" % survey_json['formid'],
                                 headers=headers)
                r.raise_for_status()
                form = r.json()
                fields = form.get('children', [])
                facility_fields = [c for c in fields if c.get('name', None) in ('facility', 'site')]
                if facility_fields:
                    survey['facilities'] = facility_fields[0]['children']
            surveys.append(survey)

        return render(request, 'kobo_forms.html', {
            'kobo_access_token_expiry': request.session.get('kobo_access_token_expiry'),
            'forms': surveys,
        })


def kobo_form_site_preview(request, kobo_form_id, site_name):
    if not is_kobo_authed(request):
        return start_kobo_oauth(request)
    else:
        headers = {
            'Authorization': "Bearer %s" % request.session.get('kobo_access_token'),
        }
        r = requests.get("https://kc.kobotoolbox.org/api/v1/forms/%s/form.json" % kobo_form_id, headers=headers)
        r.raise_for_status()
        form = r.json()
        r = requests.get("https://kc.kobotoolbox.org/api/v1/data/%s" % kobo_form_id, headers=headers)
        r.raise_for_status()
        submissions = r.json()
        site_responses = [s for s in submissions if s.get('facility', s.get('site', None)) == site_name]
        site_responses = field_per_SATA_option(form, site_responses)
        map_questions(form, site_responses)

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
        return render(request, 'survey_preview.html', {
            'site_name': site_label,
            'form_title': form['title'],
            'results': {
                'questions_dict': site_results,
                'totals': site_totals,
            }
        })


def map_questions(form, submissions):
    wrong_name = 'Select_your_gender'
    for i, q in enumerate(form.get('children', [])):
        if q.get('name', None) == wrong_name:
            q['name'] = 'gender'
            form['children'].append({
                "label": "Some questions about you",
                "type": "group",
                "children": [q],
                "name": "demographics_group"
            })
            del form['children'][i]
            for s in submissions:
                s['demographics_group/gender'] = s[wrong_name]
                del s[wrong_name]
                print s['demographics_group/gender']
            break


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
    if q_key not in dict:
        dict[q_key] = 'False'
    for val in possible_vals:
        dict['/'.join([q_key, val])] = 'False'
    for val in dict[q_key].split(' '):
        dict['/'.join([q_key, val])] = 'True'
    del dict[q_key]
    return dict


def is_kobo_authed(request):
    kobo_expiry = request.session.get('kobo_access_token_expiry', None)
    return kobo_expiry and kobo_expiry > datetime.utcnow().isoformat()


def start_kobo_oauth(request):
    user_refresh_token = KoboRefreshToken.objects.filter(pk=request.user)
    if user_refresh_token.count():
        user_refresh_token = user_refresh_token.get()
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': user_refresh_token.token,
            'redirect_uri': 'http://localhost:8000/admin/kobo-oauth'
        }
        r = requests.post("https://kc.kobotoolbox.org/o/token/",
                         params=payload,
                         auth=(settings.KOBO_CLIENT_ID, settings.KOBO_CLIENT_SECRET))
        r.raise_for_status()
        request.session['kobo_access_token'] = r.json()['access_token']
        expiry_datetime = datetime.utcnow() + timedelta(seconds=r.json()['expires_in'])
        request.session['kobo_access_token_expiry'] = expiry_datetime.isoformat()
        user_refresh_token.token = r.json()['refresh_token']
        user_refresh_token.save()
        state = request.path
        return redirect(state)
    else:
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

    user_refresh_token, created = KoboRefreshToken.objects.get_or_create(user=request.user)
    user_refresh_token.token = r.json()['refresh_token']
    user_refresh_token.save()
    return redirect(state)
