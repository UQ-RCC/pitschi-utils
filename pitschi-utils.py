#!/usr/bin/env python3

from __future__ import division, print_function, absolute_import

import sys
import argparse
import logging
import json
import subprocess
import os, shutil
import os.path
import ldap
import requests
import csv

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s [%(name)s] %(levelname)s : %(message)s')
logger = logging.getLogger(__name__)

def connect_to_ad(ad_host, ad_bind, ad_pass):
    ad_connection = ldap.initialize(ad_host)
    ad_connection.protocol_version = ldap.VERSION3
    ad_connection.simple_bind_s(ad_bind, ad_pass) 
    return ad_connection

def ppms_ad_func(args):
    if not args.ad_host or not args.ad_bind or not args.ad_pass or not args.ad_base:
        logger.error("AD info cannot be empty")
        sys.exit(1)
    if not args.ppms_url or not args.puma_key:
        logger.error("PPMS info cannot be empty")
        sys.exit(1)
        

    # now query users
    puma_api = args.ppms_url
    emails_file = open(r"ppms_emails_to_be_updated.txt","w")
    emails_file.write("count,ppms_username,ad_email\n")
    ad_connection = None
    try:
        response = requests.post(puma_api, data = {'apikey':args.puma_key, 'action': 'getusers'})
        all_users = response.text.strip().split("\n")
        count = 0 
        for user in all_users:
            user = user.strip()
            if count % 50 ==0:
                if ad_connection != None:
                    ad_connection.unbind_s()
                try:
                    ad_connection = connect_to_ad(args.ad_host, args.ad_bind, args.ad_pass)
                except ldap.INVALID_CREDENTIALS:
                    logger.error ("Your username or password is incorrect.")
                    sys.exit(0)
                except ldap.LDAPError as e:
                    if type(e.message) == dict and e.message.has_key('desc'):
                        logger.error (e.message['desc'])
                    else: 
                        logger.error (e)
                    sys.exit(0)
            count = count + 1
            # if count > 10:
            #     break
            ## get user details from ppms
            getuser_response = requests.post(puma_api, data = {'apikey':args.puma_key, 'action': 'getuser', 'login': user, 'format': 'json'})
            userdetails = getuser_response.json()
            ppms_email = userdetails['email']
            line = ""
            try: 
                searchFilter =f"(sAMAccountName={user})"
                ad_email = ad_search_email(ad_connection, args.ad_base, searchFilter).decode()
                print (f"ppms email={ppms_email} ad email={ad_email}")
                if ad_email != ppms_email:
                    line = f"{count},{user},{ad_email}\n"
            except Exception as e:
                print (e)
                line = f"{count},{user},NOT FOUND\n"
            emails_file.write(line)
                
    except Exception as e:
        logger.error(e)
    if ad_connection != None:
        ad_connection.unbind_s()
    emails_file.close()




def get_projects(ppms_url:str, puma_key: str):
    logger.debug("Querying projects")
    url = f"{ppms_url}pumapi/"
    payload=f"apikey={puma_key}&action=getprojects&active=true&format=json"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.ok:
        if response.status_code == 204:
            return []
        else:
            return response.json(strict=False)
    else:
        return []


def get_project_user(ppms_url:str, puma_key: str, projectid: int):
    logger.debug("Querying project user")
    url = f"{ppms_url}pumapi/"
    payload=f"apikey={puma_key}&action=getprojectusers&withdeactivated=false&projectid={projectid}"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.ok:
        if response.status_code == 204:
            return []
        else:
            response_txt = response.text
            return response_txt.strip().split("\n")
    else:
        return []


def get_project_members(ppms_url:str, puma_key: str, projectid: int):
    logger.debug("Querying project members")
    url = f"{ppms_url}pumapi/"
    payload=f"apikey={puma_key}&action=getprojectmember&projectid={projectid}"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.ok:
        if response.status_code == 204:
            return []
        else:
            response_txt = response.text
            _csv_reader = csv.reader(response_txt.split('\n'), delimiter=',')
            _csv_reader.__next__()
            members = []
            for row in _csv_reader:
                if(len(row) > 8):
                    _userid = int(row[1])
                    _leader = bool(row[5])
                    _admin = bool(row[6])
                    _active = bool(row[7])
                    _userlogin = row[8]
                    members.append({'id': _userid, 'login': _userlogin, 'leader': _leader, 'admin': _admin, 'active': _active})
            return members
    else:
        return []

def get_ppms_user(ppms_url:str, puma_key: str, login: str):
    url = f"{ppms_url}pumapi/"
    payload=f"apikey={puma_key}&action=getuser&login={login}&format=json"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.ok:
        if response.status_code == 204:
            raise Exception('Not found')
        else:
            return response.json(strict=False)
    else:
        raise Exception('Not found')

def get_rdm_collection(ppms_url:str, api2_key: str, qcollection_action: str, q_collection_field: str, coreid: int, projectid: int):
    url = f"{ppms_url}API2/"
    payload=f"apikey={api2_key}&action={qcollection_action}&projectId={projectid}&coreid={coreid}&outformat=json"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.ok:
        if response.status_code == 204:
            return ""
        qcollection = ""
        if len(response.json()) > 0:
            resp = response.json(strict=False)
            qcollection = resp[0].get(q_collection_field)
        return qcollection
    return ""

def get_user_groups(ppms_url:str, api2_key: str):
    url = f"{ppms_url}API2/"
    payload=f"apikey={api2_key}&action=GetUserGroups"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.ok:
        if response.status_code == 204:
            return ""
        else:
            return response.json(strict=False)
    return ""

def get_user_details(ppms_url:str, api2_key: str, userid: int):
    url = f"{ppms_url}API2/"
    payload=f"apikey={api2_key}&action=GetUserDetailsById&coreid=2&checkUserId={userid}"
    headers = {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.ok:
        if response.status_code == 204:
            return ""
        else:
            return response.json(strict=False)[0]
    return ""

def ppms_proj_ad_func(args):
    if not args.ad_host or not args.ad_bind or not args.ad_pass or not args.ad_base:
        logger.error("AD info cannot be empty")
        sys.exit(1)
    if not args.ppms_url or not args.puma_key:
        logger.error("PPMS info cannot be empty")
        sys.exit(1)
    
    projects = get_projects(args.ppms_url, args.puma_key)
    # logger.info("---------------Projects ------------------------")
    # logger.info(projects)
    relevantUsers = {}
    user_emails_file = open(r"ppms_rdm_project_emails.txt","w")
    user_emails_file.write("ppms_username,ppms_email,ppms_project\n")
    for project in projects:
        if project.get('ProjectRef') < 54:
            continue
        # elif project.get('ProjectRef') > 54:
        #     break
        logger.info(f"Checking project {project.get('ProjectRef')} - {project.get('ProjectName')}")
        rdm_collection = get_rdm_collection(args.ppms_url, args.api2_key, 'Report75', 'UQRDM Collection #', 2, project.get('ProjectRef'))
        logger.info(f"RDM={rdm_collection}")
        if rdm_collection != None and rdm_collection.strip() != '':
            logger.info(f"Project {project.get('ProjectRef')} has collection")
            users = get_project_user(args.ppms_url, args.puma_key, project.get('ProjectRef'))
            for user in users:
                user = user.strip()
                if user != '':
                    userInfo = get_ppms_user(args.ppms_url, args.puma_key, user)
                    relevantUsers[user] = userInfo.get('email')
                    user_emails_file.write(f"{user},{userInfo.get('email')},{project.get('ProjectRef')}\n")
        else:
            logger.info(f"No RDM -  ignrored")
    user_emails_file.close()
    # done looping through
    mismatch_emails_file = open(r"ppms_rdm_mismatched_emails.txt","w")
    mismatch_emails_file.write("ppms_username,ppms_email,ad_email\n")
    try:
        ad_connection = connect_to_ad(args.ad_host, args.ad_bind, args.ad_pass)
    except ldap.INVALID_CREDENTIALS:
        logger.error ("Your username or password is incorrect.")
        sys.exit(0)
    except ldap.LDAPError as e:
        if type(e.message) == dict and e.message.has_key('desc'):
            logger.error (e.message['desc'])
        else: 
            logger.error (e)
        sys.exit(0)
    count = 0
    for rUser in relevantUsers:
        if count % 5 ==0:
            if ad_connection != None:
                ad_connection.unbind_s()
            try:
                ad_connection = connect_to_ad(args.ad_host, args.ad_bind, args.ad_pass)
            except ldap.INVALID_CREDENTIALS:
                logger.error ("Your username or password is incorrect.")
                sys.exit(0)
            except ldap.LDAPError as e:
                if type(e.message) == dict and e.message.has_key('desc'):
                    logger.error (e.message['desc'])
                else: 
                    logger.error (e)
                sys.exit(0)
        count = count + 1
        try: 
            searchFilter =f"(sAMAccountName={rUser})"
            ad_email = ad_search_email(ad_connection, args.ad_base, searchFilter).decode().strip()
            print (f"ppms email={relevantUsers[rUser]} ad email={ad_email}")
            if ad_email != relevantUsers[rUser]:
                mismatch_emails_file.write(f"{rUser},{relevantUsers[rUser]},{ad_email}\n")
        except Exception as e:
            print (e)
            line = f"{user},NOT FOUND\n"
    mismatch_emails_file.close()

def ppms_proj_list_func(args):
    if not args.ppms_url or not args.puma_key or not args.api2_key :
        logger.error("PPMS info cannot be empty")
        sys.exit(1)
    projects = get_projects(args.ppms_url, args.puma_key)
    # logger.info("---------------Projects ------------------------")
    # logger.info(projects)
    usergroups = get_user_groups(args.ppms_url, args.api2_key)
    relevantUsers = {}
    user_emails_file = open(r"ppms_rdm_project_emails.txt","w")
    user_emails_file.write("projectid, projectname, email, fullname, ci\n")
    for project in projects:
        # elif project.get('ProjectRef') > 54:
        #     break
        logger.info(f"\n\n==>Checking project {project.get('ProjectRef')} - {project.get('ProjectName')}")
        rdm_collection = get_rdm_collection(args.ppms_url, args.api2_key, 'Report75', 'UQRDM Collection #', 2, project.get('ProjectRef'))
        logger.info(f"RDM={rdm_collection}")
        if rdm_collection != None and rdm_collection.strip() != '':
            logger.info(f"Project {project.get('ProjectRef')} has collection")
            members = get_project_members(args.ppms_url, args.puma_key, project.get('ProjectRef'))
            logger.info(f"members: {members}")
            for member in members:
                # if not member['leader'] and not member['admin'] and member['active']:
                if member['active']:
                    _userinfo = get_user_details(args.ppms_url, args.api2_key, member['id'])
                    logger.info(f"userinfo: {_userinfo}")
                    # get unit id
                    if _userinfo['unitId']:
                        for usergroup in usergroups:
                            if int(usergroup['UnitID']) == int(_userinfo['unitId']):
                                logger.info(f"usergroup: {usergroup}")
                                # found the group
                                _chefName = usergroup['ChefName']
                                _nameParts = _chefName.split(',')
                                if len(_nameParts) > 0:
                                    _chefName = f"{_nameParts[1]} {_nameParts[0]}"
                                user_emails_file.write(f"{project.get('ProjectRef')},{project.get('ProjectName')}, {_userinfo['email']}, {_userinfo['fullName']}, {_chefName}, {usergroup['UnitName']}\n")
        # else:
            # logger.info(f"No RDM -  ignrored")
    user_emails_file.close()


def ad_search_email(ad_connection, basedn, searchFilter, searchScope=ldap.SCOPE_SUBTREE, searchAttribute=["mail"]):
    ldap_result_id = ad_connection.search(basedn, searchScope, searchFilter, searchAttribute)
    result_type, result_data = ad_connection.result(ldap_result_id, 0)
    if (result_data == []):
        raise Exception("Not found")
    else:
        return result_data[0][-1]['mail'][0]
    

def main(arguments=sys.argv[1:]):
    parser = argparse.ArgumentParser(
        prog='pitschi_utils',
        description='Utils for pitschi')
    subparsers = parser.add_subparsers(title='sub command', help='sub command help')

    ##########################################
    ppms_ad = subparsers.add_parser(
        'ppms-ad', description='Compare PPMS and AD users', help='Compare PPMS and AD users',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ppms_ad.set_defaults(func=ppms_ad_func)
    ppms_ad.add_argument('--ad-host', help='AD host', default=0, type=str)
    ppms_ad.add_argument('--ad-bind', help='AD bind address', default=0, type=str)
    ppms_ad.add_argument('--ad-pass', help='AD pass', default=0, type=str)
    ppms_ad.add_argument('--ad-base', help='AD base dn', default=0, type=str)
    ppms_ad.add_argument('--puma-url', help='PPMS url', default=0, type=str)
    ppms_ad.add_argument('--puma-key', help='PPMS puma key', default=0, type=str)


    ppms_proj_ad = subparsers.add_parser(
        'proj-ad', description='Compare PPMS project users and AD users', help='Compare PPMS project users and AD users',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ppms_proj_ad.set_defaults(func=ppms_proj_ad_func)
    ppms_proj_ad.add_argument('--ad-host', help='AD host', default=0, type=str)
    ppms_proj_ad.add_argument('--ad-bind', help='AD bind address', default=0, type=str)
    ppms_proj_ad.add_argument('--ad-pass', help='AD pass', default=0, type=str)
    ppms_proj_ad.add_argument('--ad-base', help='AD base dn', default=0, type=str)
    ppms_proj_ad.add_argument('--ppms-url', help='PPMS url', default=0, type=str)
    ppms_proj_ad.add_argument('--puma-key', help='PPMS puma key', default=0, type=str)
    ppms_proj_ad.add_argument('--api2-key', help='api2 key', default=0, type=str)


    ppms_proj_list = subparsers.add_parser(
        'proj-list', description='List PPMS projects with users and CIs', help='List PPMS projects with users and CIs',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ppms_proj_list.set_defaults(func=ppms_proj_list_func)
    ppms_proj_list.add_argument('--ppms-url', help='PPMS url', default=0, type=str)
    ppms_proj_list.add_argument('--puma-key', help='PPMS puma key', default=0, type=str)
    ppms_proj_list.add_argument('--api2-key', help='api2 key', default=0, type=str)


    args = parser.parse_args(arguments)
    return args.func(args)

if __name__ == "__main__":
    main()