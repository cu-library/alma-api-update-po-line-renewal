"""Alma API - Update PO Line renewal date"""

from datetime import date
from typing import Callable, Set
import click
import requests
import sys
import pprint

OFFSET_LIMIT_WINDOW_SIZE = 50


class SetIDNotFound(Exception):
    """The set ID for the given set name could not be found."""


class MembersOfSetNotFound(Exception):
    """The set did not contain any members."""


class FailedPOLineUpdate(Exception):
    """An error occurred when updating a PO Line."""


def validate_renewal_date(ctx, param, value):
    """Use fromisoformat() from the date module to ensure the value is a proper date."""
    try:
        date.fromisoformat(value)
        return value
    except ValueError as e:
        raise click.BadParameter(f'{str(e)}')


def debug(r):
    """Print the url, status code, and content of a response."""
    click.echo(f'URL: {r.url}')
    click.echo(f'Status Code: {r.status_code}')
    click.echo(pprint.pformat(r.content.decode('utf=8')))


def build_can_access_url(api_domain: str, headers: dict) -> Callable[[str], bool]:
    """Returns a function which sends the request using the api domain and headers."""

    def can_access_url(url: str) -> bool:
        params = {'limit': 1}
        r = requests.get(f'https://{api_domain}{url}', params=params, headers=headers)
        if r.status_code != 200:
            debug(r)
            return False
        return True

    return can_access_url


def get_set_id(set_name: str, api_domain: str, headers: dict) -> str:
    """Search the /sets Alma API endpoint for a set with a given name, returning it's ID."""
    for offset in range(0, 1000, OFFSET_LIMIT_WINDOW_SIZE):  # If we need 1000 offsets, we've gone too far
        params = {'limit': OFFSET_LIMIT_WINDOW_SIZE, 'offset': offset}
        r = requests.get(f'https://{api_domain}/almaws/v1/conf/sets', params=params, headers=headers)
        if r.status_code != 200:
            debug(r)
            raise SetIDNotFound
        content = r.json()
        if 'set' not in content:
            raise SetIDNotFound
        for alma_set in content['set']:
            if alma_set['name'] == set_name:
                return alma_set['id']


def get_po_line_ids(set_id: str, api_domain: str, headers: dict) -> Set[str]:
    """Returns a set of PO Line IDs in a given set."""
    po_line_ids = set()
    total_po_lines = 0
    for offset in range(0, 1000, OFFSET_LIMIT_WINDOW_SIZE):  # If we need 1000 offsets, we've gone too far
        params = {'limit': OFFSET_LIMIT_WINDOW_SIZE, 'offset': offset}
        r = requests.get(f'https://{api_domain}/almaws/v1/conf/sets/{set_id}/members', params=params, headers=headers)
        if r.status_code != 200:
            debug(r)
            raise SetIDNotFound
        content = r.json()
        total_po_lines = content['total_record_count']
        if 'member' not in content:
            break
        for po_line in content['member']:
            po_line_ids.add(po_line['id'])
        # The ol' slash-r trick is used here instead of a click progress bar
        # because we don't want to make an initial HTTP request to get the total number of PO Lines in the set.
        click.echo(f'\r{len(po_line_ids)}/{total_po_lines}', nl=False)

    click.echo('')
    assert len(po_line_ids) == total_po_lines
    return po_line_ids


def update_po_line(po_line_id: str, new_renewal_date: str, new_renewal_period: int, api_domain: str, headers: dict):
    """Update the PO Line with the new renewal date and new renewal reminder period."""
    r = requests.get(f'https://{api_domain}/almaws/v1/acq/po-lines/{po_line_id}', headers=headers)
    if r.status_code != 200:
        debug(r)
        raise FailedPOLineUpdate
    content = r.json()
    content['renewal_date'] = f'{new_renewal_date}Z'
    if new_renewal_period:
        content['renewal_period'] = new_renewal_period
    r = requests.put(f'https://{api_domain}/almaws/v1/acq/po-lines/{po_line_id}', headers=headers, json=content)
    if r.status_code != 200:
        debug(r)
        raise FailedPOLineUpdate


@click.command()
@click.option('--set-name', help='The identifier for the set of PO Lines we want to update')
@click.option('--new-renewal-date', required=True, type=str, callback=validate_renewal_date,
              help='YYYY-MM-DD for the new renewal date')
@click.option('--new-renewal-period', type=click.IntRange(1, 365), help='The new renewal period')
@click.option('--api-domain', type=str, default='api-ca.hosted.exlibrisgroup.com')
@click.option('--api-key', type=str, required=True, help='Alma API Key')
@click.argument('po_line_id_args', nargs=-1)
def main(set_name, po_line_id_args, new_renewal_date, new_renewal_period, api_domain, api_key):
    """PO Line Renewal - Bulk update the renewal date and renewal period for PO Lines in Alma

    A set-name or PO_LINE_ID_ARGS must be provided. If a set-name is provided, any PO_LINE_ID_ARGS provided
    as arguments are also processed.

    The set must be itemized before processing with this tool.

    CAUTION: This version of the tool has an issue with dates and timezone handling.
    In some cases, the renewal date is set to the day before the one requested.
    Also, in some other cases, other date fields in the record (like Expected Activation Date) are
    set to a new value. The new value isn't being set explicitly by this tool.
    It is the old value of the field minus one day. This is either a bug in the Alma API itself or something this
    tool should work around.

    CAUTION: Due to limitations in the Alma API, the notes fields for any PO Line record updated using this tool
    will all have 'Created On' and 'Updated On' set to today's date, and 'Updated By' will be changed to
    'API, Ex Libris'.
    """
    # Validate input
    if not set_name and not po_line_id_args:
        sys.exit('Error: A set name or PO Line IDs must be provided.')

    # Ensure we can access the API using the provided key.
    headers = {'Authorization': f'apikey {api_key}',
               'Accept': 'application/json'}
    can_access_api = build_can_access_url(api_domain, headers)
    if not all((can_access_api('/almaws/v1/conf/sets'), can_access_api('/almaws/v1/acq/po-lines'))):
        sys.exit('Error: Unable to access both Alma API urls.')

    # If the set name is provided, get the associated PO Line IDs
    if set_name:
        try:
            set_id = get_set_id(set_name, api_domain, headers)
        except SetIDNotFound:
            sys.exit(f'Error: Unable to find set ID for "{set_name}".')
        click.echo(f'Found ID {set_id} for the set "{set_name}".')

        try:
            click.echo('Retrieving the PO Line IDs in the set...')
            po_line_ids = get_po_line_ids(set_id, api_domain, headers)
            click.echo('Done!')  # po_line_ids()
        except SetIDNotFound:
            sys.exit(f'Error: Unable to find set for ID "{set_id}".')
        except MembersOfSetNotFound:
            sys.exit(f'Error: Unable to find any members for set ID "{set_id}".')
    else:
        po_line_ids = set()

    # Update the set of PO Lines with the ones provided as arguments.
    po_line_ids.update(set(po_line_id_args))

    # Use a fancy progress bar iterator on a sorted list of the PO Line IDs
    with click.progressbar(sorted(list(po_line_ids)), show_pos=True,
                           label='Updating PO Lines') as progress_for_po_line_ids:
        for po_line_id in progress_for_po_line_ids:
            try:
                update_po_line(po_line_id, new_renewal_date, new_renewal_period, api_domain, headers)
            except FailedPOLineUpdate:
                sys.exit(f'Error: Failed to update PO Line with ID "{po_line_id}".')


if __name__ == '__main__':
    main()
