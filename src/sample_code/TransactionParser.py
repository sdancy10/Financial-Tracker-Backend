import re
from abc import ABC
from decimal import Decimal
from AuthUtil import AuthUtil
from GmailUtil import GmailUtil
import TransactionRegexPatterns

class TransactionParser:
    """
        Utility class to provide account, vendor, date and amount of a chase transaction alert email
    """
    __template_used__ = ''
    __transaction_text__ = ''
    __transaction_amt__ = ''
    __transaction_vendor__ = ''
    __transaction_account__ = ''
    __transaction_date__ = ''
    __transaction_id__ = ''
    __notification_templates__ = TransactionRegexPatterns.templates

    def get_account(self):
        return self.__transaction_account__

    def __set_account__(self, regex: str = None, value: str = None):
        if regex:
            self.__transaction_account__ = re.search(regex, self.__transaction_text__).group(0)
        else:
            self.__transaction_account__ = value

    def get_template(self):
        return self.__template_used__

    def __set_template__(self, template):
        self.__template_used__ = template

    def get_vendor(self):
        return self.__transaction_vendor__

    def __set_vendor__(self, regex: str = None, value: str = None):
        if regex:
            self.__transaction_vendor__ = re.search(regex, self.__transaction_text__).group(0)
        else:
            self.__transaction_vendor__ = value

    def get_date(self):
        return self.__transaction_date__

    def __set_date__(self, regex: str = None, value: str = None):
        try:
            if regex:
                self.__transaction_date__ = re.search(regex, self.__transaction_text__).group(0)
            else:
                self.__transaction_date__ = value
        except Exception as e:
            self.__transaction_date__ = value
            with open(self.__template_used__ + '.err', "w") as err:
                err.write(self.__transaction_text__)
                err.close()
            print(e)

    def get_transaction_amount(self):
        return self.__transaction_amt__

    def __set_transaction_amount__(self, regex: str = None, value: str = None):
        if regex:
            result = re.search(regex, self.__transaction_text__)

            if result:
                result = result.group(0).replace(',', '')
                result = float(result)
                self.__transaction_amt__ = result
        else:
            self.__transaction_amt__ = float(value.replace(',', ''))

    def get_transaction_text(self):
        return self.__transaction_text__

    def get_transaction_id(self):
        return self.__transaction_id__

    def __set_transaction_id(self, trans_id):
        self.__transaction_id__ = trans_id.replace('<', '')\
                                          .replace('>', '')

    def set_transaction_text(self, transaction_id: str, transaction_text: str, transaction_dt: str = None):
        self.__transaction_text__ = transaction_text.replace('=\r\n', '')
        self.__set_transaction_id(transaction_id)
        # Determine Transaction Email Template to use
        found_template = False
        try:
            for template_type in self.__notification_templates__.keys():
                check_group = re.search(self.__notification_templates__[template_type]['amount']
                                        , self.__transaction_text__)
                if check_group is None or found_template:
                    continue
                else:
                    self.__set_template__(template_type)
                    self.__set_vendor__(regex=self.__notification_templates__[template_type]['vendor'])
                    v = self.get_vendor().lower().__contains__('huntington is legitimate')
                    if v:
                        continue
                    found_template = True
                    if self.__notification_templates__[template_type]['iterate_results']:
                        data_list = re.findall(self.__notification_templates__[template_type]['account']
                                               , self.__transaction_text__)

                        if 'Review account' in data_list:
                            data_list.remove('Review account')
                        if 'View payment activity' in data_list:
                            data_list.remove('View payment activity')
                        if 'incremental charge' in data_list[-1]:
                            data_list.pop()
                        modified_list = []
                        for i, d in enumerate(data_list):
                            b = (('<' not in d and i % 2 != 0) or i % 2 == 0)
                            if b:
                                modified_list.append(d.lower())
                        i = 0
                        data_dict = {modified_list[i]: modified_list[i + 1] for i in range(0, len(modified_list), 2)}

                        self.__set_transaction_amount__(value=data_dict['amount'][1:])
                        date = self.__notification_templates__[template_type]['date']
                        if date:
                            self.__set_date__(regex=self.__notification_templates__[template_type]['date'])
                        else:
                            if 'posted' in data_dict.keys():
                                date = data_dict['posted']
                                #self.__set_date__(value=date)
                                self.__set_date__(value=transaction_dt)
                            else:
                                self.__set_date__(value=transaction_dt)

                        if 'merchant' in data_dict.keys():
                            self.__set_vendor__(value=data_dict['merchant'])
                        elif 'recipient' in data_dict.keys():
                            self.__set_vendor__(value=data_dict['recipient'])
                        else:
                            self.__set_vendor__(value='Direct Deposit')

                        if 'account ending in' in data_dict.keys():
                            self.__set_account__(value=data_dict['account ending in'][-5:][0:4])
                        else:
                            self.__set_account__(value=data_dict['account'][-5:][0:4])
                    else:
                        self.__set_account__(regex=self.__notification_templates__[template_type]['account'])
                        date = self.__notification_templates__[template_type]['date']
                        if date:
                            self.__set_date__(regex=self.__notification_templates__[template_type]['date'])
                        else:
                            self.__set_date__(value=transaction_dt)
                        self.__set_vendor__(regex=self.__notification_templates__[template_type]['vendor'])
                        self.__set_transaction_amount__(regex=self.__notification_templates__[template_type]['amount'])
        except Exception as e:
            # Attempt to write to a file, creating it if it doesn't exist.
            # The 'with' statement ensures the file is properly closed after writing.
            safe_file_name = self.__template_used__.replace('/', '_').replace('\\', '_')
            try:
                with open(safe_file_name + '.err', "w") as err:
                    err.write(self.__transaction_text__)
                    # No need to explicitly call err.close() as 'with' handles it.
            except Exception as file_error:
                print(f"Failed to write to file: {str(file_error)}")
            else:
                # This block executes if no exceptions were raised within the 'try' block.
                print(self.__template_used__)
                print(data_list)
                print('ERROR: ' + str(e))

    def get_dict(self):
        return {
          'id': self.get_transaction_id(),
          'template_used': self.get_template(),
          'date': self.get_date(),
          'account': self.get_account(),
          'vendor': self.get_vendor(),
          'amount': self.get_transaction_amount()
        }

    def print(self):
        print('id: ' + self.get_transaction_id())
        print('Template Type: ' + str(self.__template_used__))
        print('\tAccount: ' + str(self.get_account()))
        print('\tAmount: ' + str(self.get_transaction_amount()))
        print('\tVendor: ' + str(self.get_vendor()))
        print('\tDate: ' + str(self.get_date()))


def main():
    print('[TransactionParser] - main executed')
    # t = TransactionParser()
    # # Define the path to your file
    # file_path = './Chase Credit Cards - HTML Template.err'
    #
    # # Open the file and read its contents into a string
    # with open(file_path, 'r') as file:
    #     file_contents = file.read()
    #     t.set_transaction_text('asdf',file_contents,None)


if __name__ == '__main__':
    main()
