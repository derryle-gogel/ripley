"""
Copyright ©2023. The Regents of the University of California (Regents). All Rights Reserved.

Permission to use, copy, modify, and distribute this software and its documentation
for educational, research, and not-for-profit purposes, without fee and without a
signed licensing agreement, is hereby granted, provided that the above copyright
notice, this paragraph and the following two paragraphs appear in all copies,
modifications, and distributions.

Contact The Office of Technology Licensing, UC Berkeley, 2150 Shattuck Avenue,
Suite 510, Berkeley, CA 94720-1620, (510) 643-7201, otl@berkeley.edu,
http://ipira.berkeley.edu/industry-info for commercial licensing opportunities.

IN NO EVENT SHALL REGENTS BE LIABLE TO ANY PARTY FOR DIRECT, INDIRECT, SPECIAL,
INCIDENTAL, OR CONSEQUENTIAL DAMAGES, INCLUDING LOST PROFITS, ARISING OUT OF
THE USE OF THIS SOFTWARE AND ITS DOCUMENTATION, EVEN IF REGENTS HAS BEEN ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.

REGENTS SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE
SOFTWARE AND ACCOMPANYING DOCUMENTATION, IF ANY, PROVIDED HEREUNDER IS PROVIDED
"AS IS". REGENTS HAS NO OBLIGATION TO PROVIDE MAINTENANCE, SUPPORT, UPDATES,
ENHANCEMENTS, OR MODIFICATIONS.
"""

from flask import current_app as app, redirect, request
from flask_login import current_user, login_required
from ripley.api.errors import BadRequestError, InternalServerError, ResourceNotFoundError
from ripley.api.util import canvas_role_required, csv_download_response
from ripley.externals import canvas
from ripley.externals.redis import enqueue, get_job
from ripley.lib.berkeley_term import BerkeleyTerm
from ripley.lib.canvas_utils import canvas_section_to_api_json, canvas_site_to_api_json, get_official_sections, \
    get_teaching_terms, update_canvas_sections
from ripley.lib.http import tolerant_jsonify
from ripley.lib.util import to_bool_or_none
from ripley.merged.grade_distributions import get_grade_distribution_with_demographics, get_grade_distribution_with_enrollments
from ripley.merged.roster import canvas_site_roster, canvas_site_roster_csv
from ripley.models.job_history import JobHistory


@app.route('/api/canvas_site/provision')
def canvas_site_provision():
    return tolerant_jsonify([])


@app.route('/api/canvas_site/<canvas_site_id>')
def get_canvas_site(canvas_site_id):
    course = canvas.get_course(canvas_site_id)
    if course:
        api_json = canvas_site_to_api_json(course)
        include_users = to_bool_or_none(request.args.get('includeUsers', False))
        if include_users:
            users = []
            for user in course.get_users(include=('email', 'enrollments')):
                users.append({
                    'id': user.id,
                    'enrollments': user.enrollments,
                    'name': user.name,
                    'sortableName': user.sortable_name,
                    'uid': user.login_id if hasattr(user, 'login_id') else None,
                    'url': f"{app.config['CANVAS_API_URL']}/courses/{canvas_site_id}/users/{user.id}",
                })
            api_json['users'] = sorted(users, key=lambda u: u['sortableName'])
        return tolerant_jsonify(api_json)
    else:
        raise ResourceNotFoundError(f'No Canvas course site found with ID {canvas_site_id}')


@app.route('/api/canvas_site/<canvas_site_id>/provision/sections', methods=['POST'])
@canvas_role_required('TeacherEnrollment', 'Lead TA')
def edit_sections(canvas_site_id):
    course = canvas.get_course(canvas_site_id)
    if not course:
        raise ResourceNotFoundError(f'No Canvas course site found with ID {canvas_site_id}')
    params = request.get_json()
    section_ids_to_add = params.get('sectionIdsToAdd', [])
    section_ids_to_remove = params.get('sectionIdsToRemove', [])
    section_ids_to_update = params.get('sectionIdsToUpdate', [])
    all_section_ids = section_ids_to_add + section_ids_to_remove + section_ids_to_update
    if not len(all_section_ids):
        raise BadRequestError('Required parameters are missing.')
    job = enqueue(func=update_canvas_sections, args=(course, all_section_ids, section_ids_to_remove))
    if not job:
        raise InternalServerError('Updates cannot be completed at this time.')
    return tolerant_jsonify(
        {
            'jobId': job.id,
            'jobStatus': 'sendingRequest',
        },
    )


@app.route('/api/canvas_site/<canvas_site_id>/grade_distribution')
@canvas_role_required('TeacherEnrollment', 'Lead TA')
def get_grade_distribution(canvas_site_id):
    course = canvas.get_course(canvas_site_id)
    canvas_sections = canvas.get_course_sections(canvas_site_id)
    sis_sections = [canvas_section_to_api_json(cs) for cs in canvas_sections if cs.sis_section_id]
    distribution = {
        'canvasSite': canvas_site_to_api_json(course),
        'officialSections': sis_sections,
    }
    if sis_sections:
        term_id = sis_sections[0]['termId']
        section_ids = [s['id'] for s in sis_sections]
        demographics = get_grade_distribution_with_demographics(term_id, section_ids)
        distribution['demographics'] = demographics
        grades = {d['grade']: {
            'classSize': d['classSize'],
            'count': d['count'],
            'percentage': d['percentage'],
        } for d in demographics}
        distribution['enrollments'] = get_grade_distribution_with_enrollments(term_id, section_ids, grades)
    else:
        distribution['demographics'] = []
        distribution['enrollments'] = {}
    return tolerant_jsonify(distribution)


@app.route('/api/canvas_site/<canvas_site_id>/provision/sections')
@canvas_role_required('DesignerEnrollment', 'TeacherEnrollment', 'TaEnrollment', 'Lead TA', 'Reader')
def get_official_course_sections(canvas_site_id):
    can_edit = bool(next((role for role in current_user.canvas_site_user_roles if role in ['TeacherEnrollment', 'Lead TA']), None))
    course = canvas.get_course(canvas_site_id)
    if not course:
        raise ResourceNotFoundError(f'No Canvas course site found with ID {canvas_site_id}')
    canvas_sis_term_id = course.term['sis_term_id']
    term = BerkeleyTerm.from_canvas_sis_term_id(canvas_sis_term_id)
    official_sections, section_ids, sections = get_official_sections(canvas_site_id)
    teaching_terms = [] if not len(section_ids) else get_teaching_terms(current_user, section_ids, sections)
    return tolerant_jsonify({
        'canvasSite': {
            'canEdit': can_edit,
            'officialSections': official_sections,
            'term': term.to_api_json(),
        },
        'teachingTerms': teaching_terms,
    })


@app.route('/api/canvas_site/provision/status')
@canvas_role_required('TeacherEnrollment')
def get_provision_status():
    job_id = request.args.get('jobId', None)
    if not job_id:
        raise BadRequestError('Required parameters are missing.')

    job = get_job(job_id)
    job_status = job.get_status(refresh=True)
    job_data = job.get_meta(refresh=True)
    if 'enrollment_update_job_id' in job_data:
        enrollment_update_job = JobHistory.get_by_id(job_data['enrollment_update_job_id'])
        if enrollment_update_job.failed:
            job_status = 'failed'
        elif enrollment_update_job.finished_at:
            job_status = 'finished'
        else:
            job_status = 'started'
    if 'sis_import_id' in job_data:
        sis_import = canvas.get_sis_import(job_data['sis_import_id'])
        if not sis_import:
            raise ResourceNotFoundError(f'No SIS import with {job_data} was found.')
        return tolerant_jsonify({
            'jobStatus': job_status,
            'workflowState': sis_import.workflow_state,
            'messages': getattr(sis_import, 'processing_warnings', []),
        })
    return tolerant_jsonify({
        'jobStatus': job_status,
    })


@app.route('/api/canvas_site/<canvas_site_id>/roster')
@canvas_role_required('TeacherEnrollment', 'TaEnrollment', 'Lead TA')
def get_roster(canvas_site_id):
    return tolerant_jsonify(canvas_site_roster(canvas_site_id))


@app.route('/api/canvas_site/<canvas_site_id>/export_roster')
@canvas_role_required('TeacherEnrollment', 'TaEnrollment', 'Lead TA')
def get_roster_csv(canvas_site_id):
    return csv_download_response(**canvas_site_roster_csv(canvas_site_id))


@app.route('/redirect/canvas/<canvas_site_id>/user/<uid>')
@login_required
def redirect_to_canvas_profile(canvas_site_id, uid):
    users = canvas.get_course(canvas_site_id, api_call=False).get_users(enrollment_type='student')
    user = next((user for user in users if getattr(user, 'login_id', None) == uid), None)
    if user:
        base_url = app.config['CANVAS_API_URL']
        return redirect(f'{base_url}/courses/{canvas_site_id}/users/{user.id}')
    else:
        raise ResourceNotFoundError(f'No bCourses site with ID "{canvas_site_id}" was found.')
