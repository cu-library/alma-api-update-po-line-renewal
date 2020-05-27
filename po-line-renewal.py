"""Alma API - Update PO Line renewal date"""

from datetime import date
from typing import Callable, List
import click
import requests
import sys

OFFSET_LIMIT_WINDOW_SIZE = 50


class SetIDNotFound(Exception):
    """The set ID for the given set name could not be found"""


class MembersOfSetNotFound(Exception):
    """The set did not contain any members"""


class FailedPOLineUpdate(Exception):
    """An error occurred when updating a PO Line"""


def validate_renewal_date(ctx, param, value):
    try:
        date.fromisoformat(value)
        return value
    except ValueError as e:
        raise click.BadParameter(f'{str(e)}')


def debug(r):
    print(r.url, r.status_code)
    print(r.content.decode('utf=8'))


def build_can_access_url(api_domain: str, headers: dict) -> Callable[[str], bool]:
    def can_access_url(url: str) -> bool:
        params = {'limit': 1}
        r = requests.get(f'https://{api_domain}{url}', params=params, headers=headers)
        if r.status_code != 200:
            debug(r)
            return False
        return True

    return can_access_url


def get_set_id(set_name: str, api_domain: str, headers: dict) -> str:
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


def get_po_line_ids(set_id: str, api_domain: str, headers: dict) -> List[str]:
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
        click.echo(f'\r{len(po_line_ids)}/{total_po_lines}', nl=False)
        break # TODO REMOVE ME

    # assert len(po_line_ids) == total_po_lines TODO REMOVE COMMENT
    return sorted(list(po_line_ids))


def update_po_line(po_line_id: str, new_renewal_date: str, new_renewal_period: int, api_domain: str, headers: dict):
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
@click.option('--set-name', required=True, help='the identifier for the set of PO Lines we want to update')
@click.option('--new-renewal-date', required=True, type=str, callback=validate_renewal_date,
              help='YYYY-MM-DD for the new renewal date')
@click.option('--new-renewal-period', type=click.IntRange(1, 10), help='new renewal period')
@click.option('--api-domain', type=str, default='api-ca.hosted.exlibrisgroup.com')
@click.option('--api-key', type=str, required=True, help='Alma API Key')
def main(set_name, new_renewal_date, new_renewal_period, api_domain, api_key):
    headers = {'Authorization': f'apikey {api_key}',
               'Accept': 'application/json'}
    can_access_api = build_can_access_url(api_domain, headers)
    if not all((can_access_api('/almaws/v1/conf/sets'), can_access_api('/almaws/v1/acq/po-lines'))):
        sys.exit('Error: Unable to access both Alma API urls.')

    try:
        set_id = get_set_id(set_name, api_domain, headers)
    except SetIDNotFound:
        sys.exit(f'Error: Unable to find set ID for "{set_name}".')

    click.echo(f'Found set ID {set_id} the the set "{set_name}".')

    try:
        po_line_ids = get_po_line_ids(set_id, api_domain, headers)
    except SetIDNotFound:
        sys.exit(f'Error: Unable to find set for ID "{set_id}".')
    except MembersOfSetNotFound:
        sys.exit(f'Error: Unable to find any members for set ID "{set_id}".')

    click.echo("")

    with click.progressbar(po_line_ids) as progress_for_po_line_ids:
        for po_line_id in progress_for_po_line_ids:
            try:
                update_po_line(po_line_id, new_renewal_date, new_renewal_period, api_domain, headers)
                sys.exit() # TODO remove me
            except FailedPOLineUpdate:
                sys.exit(f'Error: Failed to update PO Line with ID "{po_line_id}".')


if __name__ == '__main__':
    main()
