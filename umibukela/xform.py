"""
This aims to be a clean implementation of xform manipulation utilities
but for now we're allowing some domain-specific data to be in here
"""


class XForm(dict):
    def __init__(self, dict):
        super(XForm, self).__init__(dict)
        for path, el in self._get_elements([], self.get('children')):
            el['path'] = path
            el['pathstr'] = pathstr(path)

    def set_by_path(self, path, el):
        return self._set_child_by_path(self, path.split('/'), el)

    def get_by_path(self, path):
        return self._get_child_by_path(self, path.split('/'))

    def del_by_path(self, path):
        return self._del_child_by_path(self, path.split('/'))

    @classmethod
    def _get_child_by_path(cls, parent, path):
        for c in parent.get('children'):
            if c.get('name', '') == path[0]:
                if len(path) == 1:
                    return c
                else:
                    return cls._get_child_by_path(c, path[1:])
        return None

    @classmethod
    def _del_child_by_path(cls, parent, path):
        for i, c in enumerate(parent.get('children')):
            if c.get('name', '') == path[0]:
                if len(path) == 1:
                    parent.get('children').pop(i)
                    return True
                else:
                    return cls._del_child_by_path(c, path[1:])
        return None

    @classmethod
    def _set_child_by_path(cls, parent, path, el):
        if len(path) == 1:
            cls._del_child_by_path(parent, path)
            el['name'] = path[0]
            parent['children'].append(el)
        else:
            direct_parent = cls._get_child_by_path(parent, path[:-1])
            cls._set_child_by_path(direct_parent, [path[-1]], el)

    @classmethod
    def _get_elements(cls, path, elements):
        """Returns tuples (path_list, element)"""
        for child in elements:
            yield (path + [child['name']], child)
            if child['type'] == 'group':
                for grandchild_tuple in cls._get_elements(path + [child['name']], child['children']):
                    yield grandchild_tuple

    def questions(self):
        for path, child in self._get_elements([], self['children']):
            if child.get('type') not in {'group', 'note'}:
                yield (path, child)


class Element(object):
    def __init__(self, element, path):
        self.label = element['label']
        self.name = element['name']
        self.path = path + [element['name']]
        self.pathstr = pathstr(self.path)

    def __str__(self):
        return "%s %s" % (self.__class__, self.pathstr)


class MultipleChoice(Element):
    def __init__(self, question, path, group_labels):
        super(MultipleChoice, self).__init__(question, path)
        self.options = [Option(o, self.path) for o in question['children']]
        self.group_labels = group_labels


class Option(Element):
    pass


class SelectOne(MultipleChoice):
    pass


class SelectAllThatApply(MultipleChoice):
    pass


def pathstr(path):
    """ / separated path from array of strings"""
    return '/'.join(path)


def map_questions(form, submissions):
    form = XForm(form)
    mappings = [
        {
            'wrong_path': 'Do_you_have_any_disabilities',
            'right_path': 'demographics_group/disability'
        },
        {
            'wrong_path': 'How_old_are_you',
            'right_path': 'demographics_group/age'
        },
        {
            'wrong_path': 'Is_this_clinic_the_nearest_hea',
            'right_path': 'distance'
        },
        {
            'wrong_path': 'Where_do_you_earn_most_of_your',
            'right_path': 'demographics_group/income'
        },
        {
            'wrong_path': 'Select_your_gender',
            'right_path': 'demographics_group/gender',
        },
        {
            'wrong_path': 'Did_you_get_all_the_medication',
            'right_path': 'yes_no_group/all_medication',
        },
        {
            'wrong_path': 'How_would_you_rate_the_perform/how_good_are_the_ambulance_services_',
            'right_path': 'performance_group/ambulance',
        },
        {
            'wrong_path': 'How_would_you_rate_the_perform/does_the_clinic_have_the_necessary_equipment_in_good_working_condition_to_provide_the_services_you_need_',
            'right_path': 'performance_group/equipment',
        },
        {
            'wrong_path': 'Does_this_clinic_have_a_Clinic',
            'right_path': 'clinic_committee',
        },
        {
            'wrong_path': 'Do_you_know_what_the_Clinic_Co',
            'right_path': 'clinic_committee_function',
        },
        {
            'wrong_path': 'Do_you_think_that_this_clinic_',
            'right_path': 'clinic_feedback',
        },
        {
            'wrong_path': 'Did_you_feel_safe_in_and_aroun',
            'right_path': 'yes_no_group/safety',
        },
        {
            'wrong_path': 'Did_the_staff_respect_your_rig',
            'right_path': 'yes_no_group/examined_private',
        },
        {
            'wrong_path': 'Did_the_nurse_or_doctor_explai',
            'right_path': 'yes_no_group/consent',
        },
        {
            'wrong_path': 'Do_you_know_how_to_make_a_comp',
            'right_path': 'yes_no_group/complaint',
        },
        {
            'wrong_path': 'Do_you_think_that_the_clinic_w',
            'right_path': 'yes_no_group/complaint_response',
        },
        {
            'wrong_path': 'How_would_you_rate_the_perform/was_the_clinic_clean_',
            'right_path': 'performance_group/clean',
        },
        {
            'wrong_path': 'How_would_you_rate_the_perform/did_the_clinic_manage_queues_well_',
            'right_path': 'performance_group/queues',
        },
        {
            'wrong_path': 'How_would_you_rate_the_perform/did_the_administrative_staff_treat_you_respectfully_',
            'right_path': 'performance_group/respect_admin',
        },
        {
            'wrong_path': 'How_would_you_rate_the_perform/did_the_health_professionals_doctors_and_nurses_treat_you_respectfully_',
            'right_path': 'performance_group/respect_professionals',
        },
    ]
    for mapping in mappings:
        q = form.get_by_path(mapping['wrong_path'])
        if q:
            path = mapping['right_path'].split('/')
            group_path = path[:-1]
            if group_path:
                group = form.get_by_path('/'.join(group_path))
                if not group:
                    group = {
                        "label": '',
                        "type": "group",
                        "children": [],
                    }
                    form.set_by_path('/'.join(group_path), group)
            form.del_by_path(mapping['wrong_path'])
            form.set_by_path(mapping['right_path'], q)
            for s in submissions:
                if q['type'] == 'select all that apply':
                    for k, v in s.iteritems():
                        if k.startswith(mapping['wrong_path'] + '/'):
                            wrong_path = k
                            right_path = k.replace(mapping['wrong_path'], mapping['right_path'], 1)
                            s[right_path] = s[wrong_path]
                            del s[wrong_path]
                else:
                    s[mapping['right_path']] = s[mapping['wrong_path']]
                    del s[mapping['wrong_path']]


def map_form(form, submissions, map_to_form):
    form = XForm(form)
    map_to_form = XForm(map_to_form)
    for path, q in map_to_form.questions():
        if 'from_path' in q:
            option_mapping = {}
            for option in q['children']:
                option_mapping[option['from_name']] = option['name']
            if q['type'] == 'select all that apply':
                for o in q['children']:
                    wrong_pathstr = q['from_path'] + '/' + o['from_name']
                    right_pathstr = pathstr(path + [o['name']])
                    for s in submissions:
                        s[right_pathstr] = s[wrong_pathstr]
                        del s[wrong_pathstr]
            else:
                wrong_pathstr = q['from_path']
                right_pathstr = pathstr(path)
                for s in submissions:
                    s[right_pathstr] = option_mapping[s[wrong_pathstr]]
                    del s[wrong_pathstr]


def simplify_perf_group(form, responses):
    """Raise exception if the assumptions about the categories are wrong"""
    label_to_simple = {
        'very poor': 'negative',
        'very poorly': 'negative',
        'not at all': 'negative',
        'mostly not': 'negative',
        'poor': 'negative',
        'not good, not bad': 'neutral',
        'not sure': 'neutral',
        'yes, sometimes': 'positive',
        'yes, definitely': 'positive',
        'well': 'positive',
        'good': 'positive',
        'mostly well': 'positive',
        'excellent': 'positive',
        'very well': 'positive',
    }
    orig_name_to_simple = {'n/a': 'n/a'}
    perf_questions = []
    for child in form['children']:
        if child.get('type', None) == 'group' and child.get('name', None) == 'performance_group':
            for q in child.get('children'):
                if q.get('type') == 'select one':
                    perf_questions.append('performance_group/%s' % q.get('name'))
                    for o in q.get('children'):
                        name = o['name']
                        label = o['label']
                        orig_name_to_simple[name] = label_to_simple[label.lower()]
                    q['children'] = [
                        {
                            "name": "negative",
                            "label": "Negative",
                        },
                        {
                            "name": "neutral",
                            "label": "Neutral",
                        },
                        {
                            "name": "positive",
                            "label": "Positive",
                        },
                    ]
    for response in responses:
        for key, val in response.iteritems():
            if key in perf_questions:
                response[key] = orig_name_to_simple[val]


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


def skipped_as_na(form, submissions):
    """
    Set the value of unanswered questions to "n/a" as formhub csvwriter did.
    """
    for path, q in XForm(form).questions():
        for s in submissions:
            if pathstr(path) not in s:
                s[pathstr(path)] = 'n/a'
    return submissions
