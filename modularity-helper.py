from os import getenv
from io import BytesIO
try:
    from koji import ClientSession as ServerProxy
except ImportError:
    from xmlrpc.client import ServerProxy

from babel.messages import pofile
from flask import Flask, request, jsonify
from ModulemdTranslationHelpers import get_module_catalog_from_tags
from ModulemdTranslationHelpers.Fedora import get_fedora_rawhide_version
from ModulemdTranslationHelpers.Fedora import get_tags_for_fedora_branch
from ModulemdTranslationHelpers.Fedora import KOJI_URL

from apscheduler.schedulers.background import BackgroundScheduler

application = Flask(__name__)

koji_url = getenv('KOJI_URL', KOJI_URL)

@application.route("/alive")
def heartbeat():
    return jsonify({'result': 'Succeeded'})

@application.route("/pot")
def get_pot():
    result = dict()
    result['state'] = 'Failed'

    koji_session = ServerProxy(koji_url)

    if 'branch' not in request.args:
        input_branch = 'rawhide'
    else:
        input_branch = str(request.args['branch'])

    if input_branch == 'rawhide':
        result['branch'] = get_fedora_rawhide_version(koji_session,
                                                      application.debug)
    else:
        result['branch'] = input_branch

    # Retrieve content
    tags = get_tags_for_fedora_branch(result['branch'])
    catalog = get_module_catalog_from_tags(koji_session, tags,
                                           application.debug)

    potfile_io = BytesIO()
    pofile.write_po(potfile_io, catalog, sort_by_file=True)

    result['potfile'] = potfile_io.getvalue().decode('utf8')

    result['state'] = 'Succeeded'

    return jsonify(result)


def main():
    def test_job():
        import sys
        print('I am working...', file=sys.stderr)

    scheduler = BackgroundScheduler()
    scheduler.add_job(test_job, 'interval', seconds=5)
    scheduler.start()

    application.run()


if __name__ == "__main__":
    main()
