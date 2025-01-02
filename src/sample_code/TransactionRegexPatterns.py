templates = \
    {
        'Chase External Transfer':
            {
                'iterate_results': False
                , 'account': '(?<=ending in )(\d*)(?=.)'
                , 'amount': '(?<=A \$)(.*)(?= external)'
                , 'vendor': '(?<=to )(.*)(?= on)'
                , 'date': ''
            },
        'Chase Debit Card':
            {
                'iterate_results': False
                , 'account': '(?<=ending in )(\d*)(?=.)'
                , 'amount': '(?<=A \$)(.*)(?= debit)'
                , 'vendor': '(?<=to )(.*)(?= on)'
                , 'date': ''
            }
        , 'Chase Checking Acct - Bill Pay':
        {
            'iterate_results': False
            , 'account': '(?<=ending in )(\d*)(?=.)'
            , 'amount': '(?<=(\$))(.*)(?= payment to)'
            , 'vendor': '(?<=to )(.*)(?= on )'
            , 'date': '(?<=on )(.*)(?= ex)'
        }
        , 'Chase Credit Cards - ??':
        {
            'iterate_results': False
            , 'account': '(?<=ending in )(\d*)(?=.)'
            , 'amount': '(?<=charge of \(\$...\) )(.*)(?= at (.*) on)'
            , 'vendor': '(?<=at )(.*)(?= has)'
            , 'date': ''
        }
        , 'US Bank - Credit Card':
        {
            'iterate_results': False
            , 'account': '(?<=card ending in )[\d]{4}'
            , 'amount': '(?<=charged \$)(.*)(?=  at)'
            , 'vendor': '(?<=at )(.*)(?=. A)'
            , 'date': ''
        }
        , 'Target Credit Card':
        {
            'iterate_results': False
            , 'account': '(?<=ending in )[\d]{4}'
            , 'amount': '(?<=transaction of \$)(\d{1,3}(?:,\d{3})*(?:\.\d+)?)(?= at)'
            , 'vendor': '(?<= at )(.*)(?= was)'
            , 'date': ''
        }
        , 'Capital One Credit Card':
        {
            'iterate_results': False
            , 'account': '(?<=Account ending in )[\d]{4}'
            , 'amount': '(?<=(\$))(.*)(?= was )'
            , 'vendor': '(?<= at )(.*)(?=, a)'
            , 'date': ''
        }
        , 'Discover Credit Card':
        {
            'iterate_results': False
            , 'account': '(?<=Last 4 #:&nbsp;)(\d{4})'
            , 'amount': '(?<=(\$))(.*)(?=<br\/>)'
            , 'vendor': '(?<=(Merchant: ))(.*)(?=<br\/>)'
            , 'date': '(?<=(Date: ))(.*)(?=<br\/>)'
        }
        ,'Huntington Checking/Savings':
        {
            'iterate_results':False
            ,'account': '(?<=CK)(\d{4})'
            ,'amount': '(?<=for \$)(\d{1,3}(?:,\d{3})*(\.\d+)?|\d+(?:\.\d+)?)\b(?=| at)'
            ,'vendor': '(?<= at )(.*)(?= from)'
            ,'date': ''#'(?<=as of )(.*)(?=\.)'
        }
        ,'Huntington Checking/Savings Deposit':
        {
            'iterate_results':False
            ,'account': '(?<=CK)(\d{4})'
            ,'amount': '(?<=for \$)(([0-9,.]+)*)'
            ,'vendor': '(?<= from )(.*)(?= to)'
            ,'date': ''#'(?<=as of )(.*)(?=\.)'
        }
        ,'Huntington Checking/Savings Deposit2':
        {
            'iterate_results':False
            ,'account': '(?<=CK)(\d{4})'
            ,'amount': '(?<=for \$)(([0-9,.]+)*)'
            ,'vendor': '(?<= at )(.*)(?= from)'
            ,'date': ''#'(?<=as of )(.*)(?=\.)'
        }
        , 'Chase Credit Cards - HTML Template':
        {
            'iterate_results': True
            , 'account': '<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>'
            , 'amount': '<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>'
            , 'vendor': '<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>'
            , 'date': ''
        }
    }
