import base64
import subprocess
from getpass import getpass
from configparser import ConfigParser
from os import path
from requests_ntlm import HttpNtlmAuth
import requests


class AuthUtil(object):
    """
    Authentication Utility to aid w/ retrieval of
    user name & password credentials without
    exposing credentials in code

    """
    def __init__(self,
                 local_path: str = None,
                 cred_file_nm: str = None,
                 key_string: str = None):
        """

        :param local_path:
        :param cred_file_nm:
        :param key_string:
        """
        self.user_nm = ''
        self.user_pw = ''
        if cred_file_nm:
            self.cred_file_nm = cred_file_nm
        else:
            self.cred_file_nm = 'credentials.txt'

        if local_path:
            self.local_path = local_path
        else:
            self.local_path = 'C:/'

        if key_string:
            self.key_string = key_string
        else:
            self.key_string = subprocess\
                .check_output('wmic csproduct get uuid')\
                .decode().split('\n')[1].strip()

        self.get_local_credentials()

    @staticmethod
    def __encode(key: str, unencrypted_str: str):
        """
        Return encoded string
        :param key:
        :param unencrypted_str:
        :return:
        """
        enc = []
        for i in range(len(unencrypted_str)):
            key_c = key[i % len(key)]
            enc_c = chr((ord(unencrypted_str[i]) + ord(key_c)) % 256)
            enc.append(enc_c)
        return base64.urlsafe_b64encode(''.join(enc).encode()).decode()

    @staticmethod
    def __decode(key: str, encrypted_str: str) -> str:
        """

        :param key:
        :param encrypted_str:
        :return:
        """
        dec = []
        enc = base64.urlsafe_b64decode(encrypted_str).decode()
        for i in range(len(enc)):
            key_c = key[i % len(key)]
            dec_c = chr((256 + ord(enc[i]) - ord(key_c)) % 256)
            dec.append(dec_c)
        return ''.join(dec)

    def __create_local_credentials(self,
                                   auth_system: str = 'google') -> dict:
        self.user_nm = input("Account/User Name: ")
        self.user_pw = getpass('Account/User Password: ')
        full_path = self.local_path + self.cred_file_nm
        cred_writer = ConfigParser()
        cred_writer[auth_system] = {
            'user_nm': self.__encode(key=self.key_string,
                                     unencrypted_str=self.user_nm),
            'user_pw': self.__encode(key=self.key_string,
                                     unencrypted_str=self.user_pw)
        }
        with open(full_path, 'a') as cfg:
            cred_writer.write(cfg)
            cfg.close()
        return {
            'user_nm': self.user_nm,
            'user_pw': self.user_pw
        }

    def get_local_credentials(self, auth_system: str = 'google') -> dict:
        full_path = self.local_path + self.cred_file_nm
        if path.exists(full_path):
            config = ConfigParser()
            config.read(full_path)
            if config.has_section(auth_system):
                self.user_nm = self.__decode(
                    key=self.key_string,
                    encrypted_str=config[auth_system]['user_nm'])
                self.user_pw = self.__decode(
                    key=self.key_string,
                    encrypted_str=config[auth_system]['user_pw'])
                return {'user_nm': self.user_nm, 'user_pw': self.user_pw}

        return self.__create_local_credentials(auth_system)

    def get_http_ntlm_auth(self, auth_system: str = 'google') -> dict:
        """

        :param auth_system:
        :return: auth: HttpNtlmAuth object w/ connection details
        """
        acct = self.get_local_credentials(auth_system=auth_system)
        auth = HttpNtlmAuth(acct['user_nm'], acct['user_pw'])
        return auth

    def get_access_token(self, auth_system: str = 'google', auth_service_url: str = None) -> dict:
        acct = self.get_local_credentials(auth_system=auth_system)
        data = {
            'client_id': 'asdf1',
            'resource': 'USER:URI:App',
            'username': auth['user_nm'],
            'password': auth['user_pw'],
            'grant_type': 'password'
        }
        response = requests.post(auth_service_url, data=data)
        access_token = response.json().get('access_token')
        headers = {
            'content_type': 'application/json',
            'Authorization': 'Bearer {access_token}'.format(access_token=access_token)
        }
        return headers

if __name__ == '__main__':
    auth = AuthUtil()
    print(auth.key_string)
    print(auth.user_nm + ' ' + auth.user_pw)
    auth.get_local_credentials('aDer8RS94NPmPdAYGHQQpI3iWm13')
    print(auth.user_nm + ' ' + auth.user_pw)



