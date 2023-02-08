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

from canvasapi.exceptions import CanvasException
from flask import current_app as app
import psycopg2
from ripley import db
from ripley.externals import data_loch
from ripley.externals.canvas import ping_canvas
from ripley.externals.rds import log_db_error
from ripley.lib.http import tolerant_jsonify
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import text


@app.route('/api/ping')
def ping():
    canvas_ping = False
    db_ping = False
    try:
        canvas_ping = _ping_canvas()
        data_loch_ping = _data_loch_status()
        db_ping = _db_status()
    except Exception as e:
        subject = str(e)
        subject = f'{subject[:100]}...' if len(subject) > 100 else subject
        message = f'Error during /api/ping: {subject}'
        app.logger.error(message)
        app.logger.exception(e)
    finally:
        return tolerant_jsonify(
            {
                'app': True,
                'canvas': canvas_ping,
                'data_loch': data_loch_ping,
                'db': db_ping,
            },
        )


def _data_loch_status():
    rows = data_loch.safe_execute_rds('SELECT 1')
    return rows is not None


def _db_status():
    sql = text('SELECT 1')
    try:
        db.session.execute(sql)
        return True
    except psycopg2.Error as e:
        log_db_error(e, sql)
        return False
    except SQLAlchemyError as e:
        app.logger.error('Database connection error during /api/ping')
        app.logger.exception(e)
        return False


def _ping_canvas():
    try:
        return ping_canvas()
    except CanvasException as e:
        app.logger.error('Canvas error during /api/ping')
        app.logger.exception(e)
        return False
