"""
Survey response summary calculation

Calculation builds up a nested dict structure which makes referencing columns
and specific values easy. This is converted to an array structure for Django
Template Language to be able to put it on the screen.

The results nested dict looks something like
{u'demographics_group/age': {
     'label': u'How old are you?',
     'options': {
         u'under_25': {'count': {'female': 53,
                            'male': 11},
                       'idx': 0,
                       'key': ,
                       'label': u'Under 25 years old',
                       'pct': {'female': 26.903553299492383,
                               'male': 10.2803738317757}},
                       {'count': {'female': 101,
                                  'male': 56},
                        'idx': 1,
                        'key': u'26_40',
                        'label': u'26 - 40 years old',
                        'pct': {'female': 51.26903553299492,
                                'male': 52.336448598130836}},
where the keys are group path names then the q name separated by /
and options are under the options field keyed on option name.

The results array looks something like
[{'key': u'demographics_group/age',
  'label': u'How old are you?',
  'options': [{'count': {'female': 53,
                         'male': 11},
               'idx': 0,
               'key': u'under_25',
               'label': u'Under 25 years old',
               'pct': {'female': 26.903553299492383,
                       'male': 10.2803738317757}},
where questions are in an array and each question's options are
in an array under the question's options field.

Assumptions:
 - that the gender column is always called 'demographics_group/gender'
    and its values are always 'female' or 'male'
 - that the _uuid column always exists and is required
"""

from logging import getLogger
from xform import SelectOne, SelectAllThatApply
import pandas


# These are used for grouping. Trying to count them and group by them
# at the same time doesn't work.
SKIP_QUESTIONS = [['_uuid'], ['demographics_group', 'gender']]
SKIP_GROUP_NAMES = ['meta', 'formhub']
GENDER_COLUMN = 'demographics_group/gender'

log = getLogger(__name__)


def count_submissions(submissions):
    results = {}
    # per-gender counts
    cols = ['_uuid', GENDER_COLUMN]
    question_table = submissions.loc[:, cols]
    gender_counts = question_table.groupby(
        [GENDER_COLUMN]
    ).count()
    results['female'] = int(gender_counts.loc['female'])
    results['male'] = int(gender_counts.loc['male'])
    results['total'] = int(submissions.loc[:, ['_uuid']].count())

    return results


def count_options(submissions, children, path=None, group_labels=None, results=None):
    """
    returns nested dicts where the keys are the names of the XForm element
    branches to each question and each option of a question. Only multiple
    choice questions are supported.
    """
    path = path or []  # list of names in structure leading to current element
    group_labels = group_labels or []  # list of labels in groups in path
    results = results or {}  # results nested dict under construction
    for child in children:
        deeper_path = path + [child['name']]
        if deeper_path in SKIP_QUESTIONS:
            pass
        elif child.get('type') == 'group' and child['name'] in SKIP_GROUP_NAMES:
            pass
        elif child.get('type') == 'group':
            label = child.get('label')
            if not label:
                label = child['name'].replace('_', ' ').capitalize()
            deeper_group_labels = group_labels + [label]
            results = count_options(submissions, child['children'],
                                    deeper_path, deeper_group_labels, results)
        elif child.get('type') == 'select one':
            control = child.get('control', None)
            if control:
                if control.get('appearance') == 'label':
                    continue
            question = SelectOne(child, path, group_labels)
            results = count_select_one(submissions, question, results)
        elif child.get('type') == 'select all that apply':
            question = SelectAllThatApply(child, path, group_labels)
            results = count_select_all_that_apply(submissions, question, results)
        else:
            pass
    return results


def count_select_one(submissions, q, results):
    """
    assumes distinct values in question column as per formhub csvwriter
    """
    select_counts = count_select_one_selections(submissions, q)
    results = deep_set(results, [q.pathstr, 'label'], q.label)
    results = deep_set(results, [q.pathstr, 'group_labels'], q.group_labels)
    response_counts = count_select_one_responses(submissions, q)
    results = set_response_counts(q, results, response_counts)
    for idx in range(len(q.options)):
        opt = q.options[idx]
        results = deep_set(results, [q.pathstr, 'options', opt.name, 'label'], opt.label)
        results = deep_set(results, [q.pathstr, 'options', opt.name, 'idx'], idx)
        results = set_select_one_selection_counts(q, opt, results, select_counts)
    return results


def count_select_all_that_apply(submissions, q, results):
    """
    assumes column per option as per formhub csvwriter
    """
    results = deep_set(results, [q.pathstr, 'label'], q.label)
    results = deep_set(results, [q.pathstr, 'group_labels'], q.group_labels)
    response_counts = count_select_all_that_apply_responses(submissions, q)
    results = set_response_counts(q, results, response_counts)
    for idx in range(len(q.options)):
        opt = q.options[idx]
        select_counts = count_select_all_that_apply_selections(submissions, opt)
        results = deep_set(results, [q.pathstr, 'options', opt.name, 'label'], opt.label)
        results = deep_set(results, [q.pathstr, 'options', opt.name, 'idx'], idx)
        results = set_select_all_that_apply_selection_counts(q, opt, results, select_counts)
    return results


def count_select_one_selections(submissions, question):
    cols = ['_uuid', GENDER_COLUMN, question.pathstr]
    question_table = submissions.loc[:, cols]
    question_counts = question_table.groupby([GENDER_COLUMN, question.pathstr]).count()
    return question_counts


def count_select_all_that_apply_selections(submissions, option):
    """
    assumes selecting this option gives value 'True' as per formhub csvwriter
    """
    option_col = option.pathstr
    cols = [GENDER_COLUMN, option_col]
    option_table = submissions.loc[:, cols]
    option_chosen_table = option_table.where(submissions[option_col] == 'True')
    option_counts = option_chosen_table.groupby([GENDER_COLUMN]).count()
    return option_counts


def count_select_one_responses(submissions, q):
    """
    assumes that an un-answered 'select one' question column is
    set to 'n/a' as per formhub csvwriter
    """
    question_table = submissions.loc[:, [GENDER_COLUMN, q.pathstr]]
    return question_table.where(submissions[q.pathstr] != 'n/a').groupby([GENDER_COLUMN]).count()


def count_select_all_that_apply_responses(submissions, q):
    """
    assumes that an un-answered 'select all that apply' question
    has all option columns set to 'n/a' as per formhub csvwriter
    """
    some_option = q.options[0]
    question_table = submissions.loc[:, [GENDER_COLUMN, some_option.pathstr]]
    return question_table.where(
        submissions[some_option.pathstr] != 'n/a'
    ).groupby([GENDER_COLUMN]).count()


def set_select_all_that_apply_selection_counts(q, opt, results, option_table):
    for gender in ['male', 'female']:
        try:
            val = int(option_table.loc[gender])
        except KeyError:
            # values that aren't counted because they don't occur in the
            # results for this question won't be indexes in the counts
            log.debug("Question %s option %s %s not found in counts DataFrame %s",
                      q.pathstr, gender, opt.name, option_table)
            val = 0
        results = deep_set(results, [q.pathstr, 'options', opt.name, 'count', gender], val)
    return results


def set_select_one_selection_counts(q, option, results, option_table):
    for gender in ['male', 'female']:
        try:
            val = int(option_table.loc[gender, option.name])
        except KeyError:
            # values that aren't counted because they don't occur in the
            # results for this question won't be indexes in the counts
            log.debug("Question %s option %s %s not found in counts DataFrame %s",
                      q.pathstr, gender, option.name, option_table)
            val = 0

        results = deep_set(results, [q.pathstr, 'options', option.name, 'count', gender], val)
    return results


def set_response_counts(q, results, counts_table):
    total = 0
    for gender in ['male', 'female']:
        val = int(counts_table.loc[gender])
        total += val
        results = deep_set(results, [q.pathstr, 'response_count', gender], val)
    results = deep_set(results, [q.pathstr, 'response_count', 'total'], total)
    return results


def deep_set(deep_dict, path, value):
    key = path[0]
    if path[1:]:
        if key in deep_dict:
            deep_dict[key] = deep_set(deep_dict[key], path[1:], value)
        else:
            deep_dict[key] = deep_set({}, path[1:], value)
    else:
        deep_dict[key] = value

    return deep_dict


def combine_curr_hist(question_dict, prev_q_dict):
    """
    Combines two question result dicts, updating 'question_dict'
    to have 'current' and 'previous' results. The Question 'options'
    dict is replaced with an option array in the order the options occurred
    in the form.
    e.g.
    {"yes_no_group/bribe": {
        "response_count": {
            "total": 159, "male": 45, "female": 114
        },
        "options": [{"current": {
                        "count": {"male": 0, "female": 1},
                        "key": "yes",
                        "pct": {"male": 0.0, "female": 0.8771929824561403},
                        "idx": 0, "label": "Yes"
                        },
                     "prev": {"count": {"male": 0, "female": 0},
    """
    for q_key, question in question_dict.iteritems():
        options_dict = question['options']
        options_arr = [None] * len(options_dict)
        if (prev_q_dict and prev_q_dict.get(q_key)):
            prev_q = prev_q_dict.get(q_key)
            if not is_comparable(question, prev_q):
                prev_q = None
        else:
            prev_q = None

        for o_key, option in options_dict.iteritems():
            option = options_dict[o_key]
            option['key'] = o_key
            options_arr[option['idx']] = {'current': option}
            if prev_q:
                prev_o = prev_q['options'].get(o_key)
                if prev_o:
                    options_arr[option['idx']]['prev'] = prev_o

        question['options'] = options_arr  # overwrite
        question['response_count'] = {'current': question['response_count']}
        question['key'] = q_key


def is_comparable(q1, q2):
    """
    True if q1 and q2 have identical keys
    """
    return set(q1['options'].keys()) == set(q2['options'].keys())


def calc_q_percents(questions):
    """
    updates and returns a questions dict with percentages for option counts
    """
    for q_key, question in questions.iteritems():
        for o_key, option in question['options'].iteritems():
            for gender in ['female', 'male']:
                select_count = float(option['count'][gender])
                response_count = float(question['response_count'][gender])
                pct = (select_count / response_count) * 100
                deep_set(option, ['pct', gender], pct)
    return questions


def cross_site_summary(result_sets):
    """ Prepare a summary of responses from result sets from multiple sites.
    """
    responses = []
    form = None
    site_totals = {}
    for result_set in result_sets:
        # Assume that get_survey will make all surveys compatible
        # and therefore the last-set form applies to all
        form, site_responses = result_set.get_survey()
        df = pandas.DataFrame(site_responses)
        site_totals[result_set.site.id] = count_submissions(df)
        responses.extend(site_responses)

    if responses:
        df = pandas.DataFrame(responses)
        results = count_options(df, form['children'])
        results = calc_q_percents(results)
        totals = count_submissions(df)
        combine_curr_hist(results, None)
    else:
        totals = {'male': 0, 'female': 0, 'total': 0}
        results = None

    totals['per_site'] = site_totals
    return results, totals
