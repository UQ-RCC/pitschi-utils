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
    ppms_ad.add_argument('--ppms-url', help='PPMS url', default=0, type=str)
    ppms_ad.add_argument('--puma-key', help='PPMS puma key', default=0, type=str)

    args = parser.parse_args(arguments)
    return args.func(args)

if __name__ == "__main__":
    main()