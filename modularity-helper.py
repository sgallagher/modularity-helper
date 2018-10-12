from os import getenv, chdir
from io import BytesIO
try:
    from koji import ClientSession as ServerProxy
except ImportError:
    from xmlrpc.client import ServerProxy

import subprocess

from babel.messages import pofile
from flask import Flask, request, jsonify
from tempfile import TemporaryDirectory

from ModulemdTranslationHelpers import get_module_catalog_from_tags
from ModulemdTranslationHelpers.Fedora import get_fedora_rawhide_version
from ModulemdTranslationHelpers.Fedora import get_tags_for_fedora_branch
from ModulemdTranslationHelpers.Fedora import KOJI_URL

from apscheduler.schedulers.background import BackgroundScheduler

application = Flask(__name__)


def application_init():
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_pot_for_all_branches, 'interval', minutes=30)
    scheduler.start()

    # Validate that we have mandatory env vars
    zanata_user = getenv('ZANATA_USER')
    if not zanata_user:
        raise PermissionError('No Zanata user specified')

    zanata_key = getenv('ZANATA_KEY')
    if not zanata_key:
        raise PermissionError('No Zanata key specified')


potfile_name = getenv('POTFILE_NAME',
                      default='fedora-modularity-translations.pot')
zanata_url = getenv('ZANATA_URL',
                    default='https://fedora.zanata.org')
zanata_project = getenv('ZANATA_PROJECT',
                        default='fedora-modularity-translations')
zanata_user = getenv('ZANATA_USER')
zanata_key = getenv('ZANATA_KEY')

koji_url = getenv('KOJI_URL', KOJI_URL)


def get_branch(koji_session, args):
    if 'branch' not in args:
        input_branch = 'rawhide'
    else:
        input_branch = str(args['branch'])

    if input_branch == 'rawhide':
        branch = get_fedora_rawhide_version(koji_session,
                                            application.debug)
    else:
        branch = input_branch

    return branch


@application.route("/alive")
def heartbeat():
    return jsonify({'result': 'Succeeded'})


@application.route("/strings")
def get_pot():
    result = dict()
    result['state'] = 'Failed'

    koji_session = ServerProxy(koji_url)

    result['branch'] = get_branch(koji_session, request.args)

    # Retrieve content
    tags = get_tags_for_fedora_branch(result['branch'])
    catalog = get_module_catalog_from_tags(koji_session, tags,
                                           application.debug)

    potfile_io = BytesIO()
    pofile.write_po(potfile_io, catalog, sort_by_file=True)

    result['potfile'] = potfile_io.getvalue().decode('utf8')

    result['state'] = 'Succeeded'

    return jsonify(result)


def do_update_pot(koji_session, branch, debug=False):
    result = dict()
    result['state'] = 'Failed'

    result['branch'] = branch

    # Retrieve content
    tags = get_tags_for_fedora_branch(branch)
    catalog = get_module_catalog_from_tags(koji_session, tags,
                                           debug)

    with TemporaryDirectory() as tdir:
        chdir(tdir)

        # Create a temporary file to upload to Zanata
        with open(potfile_name, 'wb') as potfile:
            pofile.write_po(potfile, catalog, sort_by_file=True)

        # Use the zanata-cli to upload the pot file
        # It would be better to use the REST API directly here, but the XML
        # payload format is not documented.

        # Dump the user config locally so the key doesn't show up in the
        # process table.
        with open('zanata.ini', 'w') as inifile:
            inifile.write('[servers]\n')
            inifile.write('zanata.url=%s\n' % zanata_url)
            inifile.write('zanata.username=%s\n' % zanata_user)
            inifile.write('zanata.key=%s\n' % zanata_key)

        # Ensure that the requested branch exists in Zanata
        zanata_args = [
            '/usr/bin/zanata-cli', '-B', '-e', 'put-version',
            '--url', zanata_url,
            '--version-project', zanata_project,
            '--version-slug', branch,
            '--user-config', 'zanata.ini',
        ]
        status = subprocess.run(zanata_args, capture_output=True)
        if status.returncode or application.debug:
            print(status.stderr.decode('utf-8'))
            print(status.stdout.decode('utf-8'))
        if status.returncode:
            result['errorcode'] = status.returncode
            result['message'] = "Could not create branch in Zanata. " \
                                "Permission error?"
            return jsonify(result)

        # Update the translatable strings for this branch
        zanata_args = [
            '/usr/bin/zanata-cli', '-B', '-e', 'push',
            '--url', zanata_url,
            '--project', zanata_project,
            '--project-type', 'gettext',
            '--project-version', branch,
            '--src-dir', tdir,
            '--user-config', 'zanata.ini',
        ]
        status = subprocess.run(zanata_args, capture_output=True)
        if status.returncode or application.debug:
            print(status.stderr.decode('utf-8'))
            print(status.stdout.decode('utf-8'))
        if status.returncode:
            result['errorcode'] = status.returncode
            result['message'] = "Could not update strings in Zanata."

            return jsonify(result)

    result['state'] = 'Succeeded'
    result['message'] = 'Uploaded translatable strings for %s to Zanata' % (
        branch)

    return result


@application.route("/strings/update")
def update_pot(branch=None):
    koji_session = ServerProxy(koji_url)

    if not branch:
        branch = get_branch(koji_session, request.args)

    result = do_update_pot(koji_session, branch, debug=application.debug)

    return jsonify(result)


def update_pot_for_all_branches():
    # Get the list of supported Fedora releases
    # TODO: Detect this automatically

    for branch in ['f28', 'f29', 'f30']:
        application.logger.info("Updating translations for %s" % branch)

        koji_session = ServerProxy(koji_url)
        result = do_update_pot(koji_session, branch)
        if result['state'] == 'Failed':
            application.logger.error("%d: %s" % (
                result['errorcode'], result['message']))


application_init()


def main():
    application.run()


if __name__ == "__main__":
    main()
