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

import logging

import requests_mock
from ripley.jobs.reconfigure_canvas_test_servers_job import ReconfigureCanvasTestServersJob
from tests.util import register_canvas_uris


class TestReconfigureCanvasTestServersJob:

    def test_job_run(self, app, caplog):
        with requests_mock.Mocker() as m:
            register_canvas_uris(app, {
                'account': ['create_admin', 'get_admins'],
                'authentication_provider': ['get_authentication_providers', 'update_authentication_providers'],
                'user': ['profile_test_admin_id'],
            }, m)
            with caplog.at_level(logging.INFO):
                ReconfigureCanvasTestServersJob(app)._run()
                assert 'Updating CAS auth base on https://hard_knocks_api.instructure.com to https://auth-test.berkeley.edu/cas' in caplog.text
                assert 'Adding test admin to https://hard_knocks_api.instructure.com (id=123, login_id=test_admin_id)' in caplog.text
