#!/usr/bin/env python

import argparse
import os
import time
import subprocess
import requests # pylint: disable=import-error

import googleapiclient.discovery

from google.oauth2.service_account import Credentials
from google.cloud import redis_v1


def get_projects(service):
    # List available projects
    request = service.projects().list()

    # Collect all the projects
    projects = []
    # Paginate through the list of all available projects
    while request is not None:
        response = request.execute()
        projects.extend(response.get('projects', []))
        request = service.projects().list_next(request, response)
    return projects


def get_zones(project):
    zones = []
    compute = googleapiclient.discovery.build('compute', 'v1')
    request = compute.zones().list(project=project)
    while request is not None:
        response = request.execute()
        for zone in response['items']:
            zones.append(zone["name"])
        request = compute.zones().list_next(previous_request=request, previous_response=response)
    zones.sort()
    return zones


def get_regions(project):
    regions = []
    compute = googleapiclient.discovery.build('compute', 'v1')
    request = compute.regions().list(project=project)
    while request is not None:
        response = request.execute()
        for region in response['items']:
            regions.append(region["name"])
        request = compute.regions().list_next(previous_request=request, previous_response=response)
    regions.sort()
    return regions


# [START compute_apiary_list_instances]
def list_instances(service, project, zone):
    result = service.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None
# [END compute_apiary_list_instances]


def list_disks(service, project, zone):
    result = service.disks().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None


def list_addresses(service, project, region):
    result = service.addresses().list(project=project, region=region).execute()
    return result['items'] if 'items' in result else None


def get_external_ip(instance):
    try:
        return instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
    except KeyError:
        return "none"


def compute_instance_report(project):
    print("==== Compute Engine ====")
    compute = googleapiclient.discovery.build('compute', 'v1')

    # Compute Instances
    print("-- Instances --")
    for zone in get_zones(project):
        items = list_instances(compute, project, zone)
        if items:
            for item in items:
                print(",".join([
                    item["zone"].split('/')[-1],
                    item["name"],
                    item["status"],
                    item["machineType"].split('/')[-1],
                    item["networkInterfaces"][0]["networkIP"],
                    get_external_ip(item),
                ]))

    # Disks
    print("-- Disks --")
    for zone in get_zones(project):
        items = list_disks(compute, project, zone)
        if items:
            for item in items:
                print(",".join([
                    item["zone"].split('/')[-1],
                    item["name"],
                    item["status"],
                    item["sizeGb"],
                    ('|'.join(item["users"])).split('/')[-1],  # TODO: Refactor this to work when multiple users
                ]))

    # Addresses
    print("-- Addresses --")
    for region in get_regions(project):
        addresses = list_addresses(compute, project, region)
        if addresses:
            for item in addresses:
                print(",".join([
                    item["region"].split('/')[-1],
                    item["name"],
                    item["status"],
                    item["address"],
                    item["networkTier"],
                    item["addressType"],
                    ('|'.join(item["users"])).split('/')[-1],  # TODO: Refactor this to work when multiple users
                ]))


def list_sql_instances(sql, project):
    result = sql.instances().list(project=project).execute()
    return result['items'] if 'items' in result else None


def sql_instance_report(project):
    print("==== SQL Engine ====")
    sql = googleapiclient.discovery.build('sqladmin', 'v1beta4')

    # SQL Instances
    items = list_sql_instances(sql, project)
    for item in items:
        print(",".join([
            item["region"],
            item["gceZone"],
            item["name"],
            item["state"],
            item["databaseVersion"],
            item["settings"]["tier"],
            item["settings"]["availabilityType"],
            item["ipAddresses"][0]["ipAddress"],
            item["ipAddresses"][1]["ipAddress"],
        ]))


def list_redis_instances(service, project):
    try:
        result = service.list_instances(parent=f'projects/{project}/locations/-')
        return result
    except:
        return None


    # return result['items'] if 'items' in result else None


def redis_instance_report(project):
    print("==== Memorystore ====")
    service = redis_v1.CloudRedisClient()

    # Redis Instances
    items = list_redis_instances(service, project)
    if items:
        for item in items:
            print(",".join([
                str(item.location_id),
                str(item.display_name),
                str(item.state),
                str(item.redis_version),
                str(item.host),
                str(item.tier),
                str(item.memory_size_gb),
            ]))


def create_token():
    """
    There is no SDK for API Keys as of May 2020.
    We have to create a bearer token to submit with our HTTP requests in get_keys()
    You can create a token using google.auth.transport.requests.Request() but the scope requirement
    requires the official API to be activated and it is in early alpha / not available for most users.
    Check this URL for the API https://cloud.google.com/api-keys/docs/overview to know when it is public.
    """
    access_token = subprocess.run('gcloud auth print-access-token', shell=True, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    token = access_token.stdout
    return token


def create_service():
    """Creates the GCP Cloud Resource Service"""
    return googleapiclient.discovery.build('cloudresourcemanager', 'v1')


def api_keys_report(service, access_token, project):
    print("==== API Keys ====")
    # Use the project ID and access token to find the API keys for each project
    items = requests.get(
        f'https://apikeys.googleapis.com/v1/projects/{project}/apiKeys',
        params={'access_token': access_token}
    ).json()

    if "error" not in items:  # Removes 403 permission errors from returning
        if items:
            for item in items["keys"]:
                print(",".join([
                    item["keyId"],
                    item["displayName"],
                    item["currentKey"],
                    item["createTime"],
                ]))


# [START compute_apiary_run]
def main():
    # Configure
    access_token = create_token()
    service = create_service()

    projects = get_projects(service)

    for project in projects:
        print(f'======================== {project["projectId"]}')
        compute_instance_report(project["projectId"])
        sql_instance_report(project["projectId"])
        redis_instance_report(project["projectId"])
        api_keys_report(service, access_token, project["projectId"])

    print("======================== END")


if __name__ == '__main__':
    # parser = argparse.ArgumentParser(
    #     description=__doc__,
    #     formatter_class=argparse.RawDescriptionHelpFormatter)
    # parser.add_argument('project_id', help='Your Google Cloud project ID.')
    #
    # args = parser.parse_args()
    #
    # # main(args.project_id)

    # For all projects
    main()
# [END compute_apiary_run]
