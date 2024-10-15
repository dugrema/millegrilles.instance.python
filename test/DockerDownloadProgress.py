import asyncio
import docker
import logging
import json
import math

from typing import Optional


def download_package(client: docker.client.DockerClient, repository: str, tag: Optional[str] = None):
    pull_generator = client.api.pull(repository, tag, stream=True)
    layers = dict()
    for line in pull_generator:
        print('** %s **' % line)
        value = json.loads(line)

        try:
            status = value['status']
            layer_id = value['id']
        except KeyError:
            # Other status, like digest (all done)
            continue

        try:
            progress_detail = value['progressDetail']
        except KeyError:
            progress_detail = None

        if status == 'Downloading':
            try:
                layers[layer_id].update(progress_detail)
            except KeyError:
                layers[layer_id] = progress_detail
        elif status == 'Pull complete':
            layers[layer_id]['complete'] = True
        elif status == 'Already exists':
            layers[layer_id] = {'complete': True}
        elif status == 'Pulling fs layer':
            layers[layer_id] = {'complete': False, 'current': 0}

        print("Status ", layers)
        show_status(layers)


def show_status(layers: dict[str, dict]):
    all_totals_known = True
    current_size = 0
    total_size = 0
    incomplete = 0
    for key, value in layers.items():
        if value.get('complete') is not True:
            incomplete = incomplete + 1
        try:
            total_size = total_size + value['total']
        except KeyError:
            if value.get('complete') is not True:
                all_totals_known = False
        try:
            current_size = current_size + value['current']
        except KeyError:
            pass

    if all_totals_known and total_size > 0:
        # Calculer pct
        pct = math.floor(current_size / total_size * 100)
        print("Downloading: %d%% (%d/%d bytes), left to process: %d" % (pct, current_size, total_size, incomplete))
    else:
        # Montrer progres connu
        print("Downloading: %d/%d+ bytes, left to process: %d" % (current_size, total_size, incomplete))

async def main():
    client = docker.from_env()
    await asyncio.to_thread(download_package, client, 'redis', '7')


if __name__ == '__main__':
    asyncio.run(main())
