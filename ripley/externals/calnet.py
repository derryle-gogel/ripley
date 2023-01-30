"""
Copyright ©2022. The Regents of the University of California (Regents). All Rights Reserved.

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
import ssl

import ldap3

SCHEMA_DICT = {
    'berkeleyEduAlternateID': 'email',
    'berkeleyEduPrimaryDeptUnit': 'primary_dept_code',
    'departmentNumber': 'dept_code',
    'givenName': 'first_name',
    'sn': 'last_name',
    'uid': 'uid',
}

BATCH_QUERY_MAXIMUM = 500


def client(app):
    return Client(app)


class Client:

    def __init__(self, app):
        self.app = app
        self.host = app.config['LDAP_HOST']
        self.bind = app.config['LDAP_BIND']
        self.password = app.config['LDAP_PASSWORD']
        tls = ldap3.Tls(validate=ssl.CERT_REQUIRED)
        server = ldap3.Server(self.host, port=636, use_ssl=True, get_info=ldap3.ALL, tls=tls)
        self.server = server

    def connect(self):
        conn = ldap3.Connection(self.server, user=self.bind, password=self.password, auto_bind=ldap3.AUTO_BIND_TLS_BEFORE_BIND)
        return conn

    def search_uids(self, uids, search_expired=False):
        all_out = []
        for i in range(0, len(uids), BATCH_QUERY_MAXIMUM):
            uids_batch = uids[i:i + BATCH_QUERY_MAXIMUM]
            with self.connect() as conn:
                search_filter = self._ldap_search_filter(uids_batch, 'uid', search_expired)
                conn.search('dc=berkeley,dc=edu', search_filter, attributes=ldap3.ALL_ATTRIBUTES)
                all_out += [_attributes_to_dict(entry, search_expired) for entry in conn.entries]
        return all_out

    @classmethod
    def _ldap_search_filter(cls, ids, id_type, search_expired=False):
        ids_filter = ''.join(f'({id_type}={_id})' for _id in ids)
        ou_scope = '(ou=expired people)' if search_expired else '(ou=people) (ou=advcon people)'
        return f"""(&
            (objectclass=person)
            (|
                {ids_filter}
            )
            (|
                { ou_scope }
            )
        )"""


def _attributes_to_dict(entry, expired_per_ldap):
    out = dict.fromkeys(SCHEMA_DICT.values(), None)
    out['expired'] = expired_per_ldap
    # ldap3's entry.entry_attributes_as_dict would work for us, except that it wraps a single value as a list.
    for attr in SCHEMA_DICT:
        if attr in entry.entry_attributes:
            out[SCHEMA_DICT[attr]] = entry[attr].value
    return out
