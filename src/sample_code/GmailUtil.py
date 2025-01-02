import imaplib
import email
import os
import socket
import time
from multiprocessing.pool import ThreadPool as Pool
from AuthUtil import AuthUtil


class GmailUtil:
    __conn = None
    __mailboxes = []
    __result = []

    def create_folder(self, folder_name="backup"):
        """
        Creates a folder to store all mails
        """
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

    def __extract_body(self, payload):
        """
        returns the email body from the payload
        """
        if isinstance(payload, str):
            return payload
        else:
            return '\n'.join([self.__extract_body(part.get_payload()) for part in payload])

    def create_connection(self, user_name, password):
        """
        logs into the email service provider using the provided username and password
        :return: connection object for imaplib
        """
        self.__result = []
        self.__conn = imaplib.IMAP4_SSL(host="imap.gmail.com", port=993)
        tcp_no_delay = 1
        self.__conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, tcp_no_delay)

        try:
            self.__conn.login(user_name, password)
        except Exception as e:
            print("Could not login", e)
        return self.__conn

    def get_mailboxes(self):
        """
        Displays the mail boxes in your email client
        :param conn: imaplib object
        """

        for n, item in enumerate(self.__conn.list()[1]):
            mailbox = item.decode("utf-8")
            self.__mailboxes.append(mailbox[mailbox.index("\"/\"") + 4:])
            print(n, mailbox[mailbox.index("\"/\"") + 4:])
        return self.__mailboxes

    def set_mailbox(self, mailbox):
        """
        select a mailbox to search through
        :param mailbox: name of the mailbox
        """
        return self.__conn.select(mailbox)

    def __parse_msg_data(self, msg_data):
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_string(response_part[1].decode("utf-8"))
                id = msg['Message-ID']
                subject = msg['subject']
                payload = msg.get_payload()
                body = self.__extract_body(payload)
                result = {'id': id, 'message': msg, 'subject': subject, 'payload': payload, 'body': body}
                self.__result.append(result)
        return self.__result

    def get_emails(self, search_param):
        if len(search_param) == 0:
            search_param = "UNSEEN"
        typ, data = self.__conn.search(None, search_param)

        try:
            for num in data[0].split():
                _, msg_data = self.__conn.fetch(num, '(RFC822)')
                self.__conn.store(num, '+FLAGS', '\Seen')
                self.__parse_msg_data(msg_data)
        except Exception as e:
            print("EXCEPTION OCCURED:", e)
            self.__conn.logout()
        finally:
            self.__conn.close()
        return self.__result

    def get_email_by_id(self, email_id):
        """
        Retrieves an email by its message id
        """
        try:
            typ, data = self.__conn.search(None, 'HEADER', 'Message-ID', email_id)
            if data[0]:
                num = data[0].split()[0]
                _, msg_data = self.__conn.fetch(num, '(RFC822)')
                msg = email.message_from_string(msg_data[0][1].decode("utf-8"))
                subject = msg['subject']
                payload = msg.get_payload()
                body = self.__extract_body(payload)
                result = {'id': email_id, 'message': msg, 'subject': subject, 'payload': payload, 'body': body}
                return result
            else:
                return None
        except Exception as e:
            print("EXCEPTION OCCURED:", e)
            self.__conn.logout()
            return None

if __name__ == '__main__':

    gmailUtil = GmailUtil()
    auth = AuthUtil()
    auth.get_local_credentials('aDer8RS94NPmPdAYGHQQpI3iWm13')
    user = auth.user_nm
    pwd = auth.user_pw
    conn = gmailUtil.create_connection(user, pwd)
    mailbox_choice = 'Transactions'
    gmailUtil.set_mailbox(mailbox_choice)
    emails = ['728995165.362959.1699188641411@dep-dmg-orchestrator-scheduled-alert-delivery-dmg-prod-55bsvdq6']
    for e in emails:
        t = gmailUtil.get_email_by_id(e)
        print(t['message'])
        print(t['message'].__str__().__contains__('noreply.pncalerts@pnc.com'))
    # search_param = ''
    # if len(search_param) == 0:
    #     search_param = "ALL"
    # start_time = time.perf_counter()
    # results = gmailUtil.get_emails(search_param)
    # end_time = time.perf_counter()
    # print('Execution Time: ' + str((end_time - start_time)))
