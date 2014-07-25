from time import sleep
# export PYTHONPATH=$PYTHONPATH:/oanda/oandapy
__author__ = 'ubuntu01'

#todo code cleanup, change variable away from oanda3 as we run any acct. also check comments
#todo set up spread awarenes, so we don't do trades if spread is too much
#todo change trades so they come with a range that we will accept
#todo create robot05.sh
#todo move money from robot03 to robot05
#todo log info in a logfile
#todo support for other leverage limits than 50 and 90
#todo log important info in another logfile
#todo start up a stock shorting robot with as little money as possible - perhaps a few different leverage profiles
#todo (big task) implement correct s2 trading
#todo take profit module (might need to transfer money, probably not available in api)
#todo if logstring is not different then dont print it
#todo also print the time gotten from the srv
#todo put in sanity checks that for instance blocks trading more than N orders each hour
#todo test a gold like scenario with lowered margin (alternatively buying and selling bc we go off limits)


import io
import json
import os.path
import math
import argparse
import os
import datetime

program_name = "Robot Runner"

print(os.environ['PYTHONPATH'].split(os.pathsep))

import oandapy


settings = {}

settings_file = 'settings.json'

argparser = argparse.ArgumentParser(description="run a trade system")
argparser.add_argument('--account', type=int, help='the account number to trade')
argparser.add_argument('--pair', help='the pair to trade (short)')
argparser.add_argument('--maxpos', type=int, default=999999999999, help='the max. number of units to own in this pair')
argparser.add_argument('--MCP_buytrigger', type=int, default=50,
                       help='MCP below this level triggers buy action up to this level')
argparser.add_argument('--MCP_selltrigger', type=int, default=90,
                       help='MCP below this level triggers sell action down to this level')
argparser.add_argument('--settings',default='settings.json' )

args = argparser.parse_args()
settings_file = args.settings

if os.path.isfile(settings_file):
    with open(settings_file) as data_file:
        settings = json.load(data_file)
else:
    print("no settings file, creating a new one. This one need to have its access_token set correctly!")
    #todo remove below line as it contains secret key
    settings = {"access_token": "cadcxxxxxxxxxxxxxxxxxxxxxxx573ee-d1bxxxxxxxxxxxxxxxxxxxxxxxx1a1f1",
                "environment": "live",
                "crosses": [
                    {"direction": 0, "instrument": "EUR_USD", "max_spread": 0.99, "weight": 0.01},
                    {"direction": 0, "instrument": "AUD_USD", "max_spread": 1.32, "weight": 0.02},
                    {"direction": 0, "instrument": "GBP_USD", "max_spread": 1.76, "weight": 0.01}]
    }
    with io.open(settings_file, 'w') as f:
        f.write(unicode(json.dumps(settings)))
        print("written settings file %s", f.name)

print("%s V0.001 started" % program_name)

robot_instrument = args.pair  #"USB10Y_USD"
robot_accountid = args.account  #475120
robot_mcpbuytrigger = args.MCP_buytrigger  # 50
robot_mcpselltrigger = args.MCP_selltrigger  #90
robot_maxpos = args.maxpos

#curl -H "Authorization: Bearer cadccca50a597cc271eba795d89573ee-d1b8c0ba147dffb7b639e7f784d1a1f1" https://api-fxpractice.oanda.com/v1/accounts
#oanda = oandapy.API(environment="practice",  access_token=None)
oanda = oandapy.API(environment=settings['environment'], access_token=settings['access_token'])

tmp = oanda.get_instruments(robot_accountid)

# build a commasep list of instruments that will be used to call onada to get prices
instrumentscsv=""
for cross in settings['crosses']:
    instrumentscsv=instrumentscsv+cross['instrument']+","

instrumentscsv=instrumentscsv[:-1]



sleep_seconds = 1
last_robot_NAV = 0

while True:
    #trade oanda3
    sleep(sleep_seconds)
    try:
        eur_usd_response = oanda.get_prices(instruments="EUR_USD")
        eur_usd_prices = eur_usd_response.get("prices")
        eur_usd_bid = eur_usd_prices[0].get("bid")

        #gather account information
        account_info = oanda.get_account(robot_accountid)
        robot_NAV = account_info['balance'] + account_info['unrealizedPl']
        robot_margin_used = account_info['marginUsed']
        robot_margin_rate = account_info['marginRate']  #typically 0.02
        robot_margin_rate_inv = 1.0 / robot_margin_rate  #typically 50
        robot_margin_closeout_pct = robot_margin_used * robot_margin_rate_inv / robot_NAV  #need to calculate myself if avail =0
        robot_marginAvail = account_info['marginAvail']  #more precize than calculating it myself
        #below not precise if positions exist with stuff that has margin demands other than 0.02
        #so don't take too seriously
        robot_position_size = robot_margin_used * robot_margin_rate_inv

        response = oanda.get_prices(instruments=instrumentscsv)

        ix=0
        for instrument_curprice in response['prices']:
            ordercomment=""
            instrument_totrade = settings['crosses'][ix]
            ix+=1
            instrumentname1 =instrument_curprice['instrument']
            instrumentname2 =instrument_totrade['instrument']
            if instrumentname1==instrumentname2:
                if 'status' in instrument_curprice:
                    robot_curstatus = instrument_curprice['status']
                else:
                    robot_curstatus = 'live'

                #these 3 can be read outside the if, as they are already
                #taken in from oanda. so no extra traffic
                robot_curbid = instrument_curprice['bid']
                robot_curask = instrument_curprice['ask']
                robot_curspread = robot_curask - robot_curbid
                last_checked_position=instrumentname1 # just for display
                last_checked_position_units =0  # unknown. just for display

                if robot_curstatus == 'live':
                    if robot_curspread < instrument_totrade['max_spread']:
                        position_size=0
                        try:
                            position = oanda.get_position(robot_accountid,instrumentname1) #in usd
                            position_size = position['units']
                            last_checked_position_units=position_size
                            last_checked_position=instrumentname1
                        except Exception as e:
                            ordercomment=""
                            # ordercomment="exception when reading position size %s" %str(e)

                        unit_size_in_euros  =  1.0 / eur_usd_bid
                        # assume it is something_usd so add test if we do non usd crosses one day
                        openside = "sell"  # bc all usd something are short usd
                        closeside  ="buy"  # otherwise we should look at direction
                        if instrumentname1[:3]!="USD":
                            unit_size_in_euros = instrument_curprice['ask']  / eur_usd_bid
                            if instrument_totrade['direction']==0:
                                openside = "buy"
                                closeside = "sell"

                            unlevered_target_possize = robot_NAV / unit_size_in_euros  * instrument_totrade['weight'] #in usd
                            positionsize_min = robot_mcpbuytrigger * unlevered_target_possize
                            positionsize_max = robot_mcpselltrigger * unlevered_target_possize
                            if  (position_size < positionsize_min) :
                                units_to_open = int(math.floor(positionsize_min - position_size))
                                if units_to_open>0 and robot_marginAvail * unit_size_in_euros * robot_margin_rate_inv >units_to_open:
                                    try:
                                        res = oanda.create_order(robot_accountid, instrument=instrumentname1,
                                                                 units=units_to_open, side=openside, type="market")
                                        ordercomment = "Opened %04d now %06d total. at %.4f" % (units_to_open, res['tradeOpened']['units'], res['price'])
                                    except Exception as e:
                                        ordercomment = "exception when trying to create opening order %s" % str(e)
                                    sleep_seconds = 1  # be quick to follow up after order

                            if (position_size > positionsize_max) and (position_size>1):
                                units_to_close = int(math.floor( position_size -positionsize_max))
                                # IN THE NON USD VERSION DONT CLOSE IF A CLOSE GETS US TO 0 OR BELOW POSITIONSIZE_MIN
                                #no need to test if we have margin enough as we are reducing
                                if (units_to_close>0):
                                    try:
                                        res = oanda.create_order(robot_accountid, instrument=instrumentname1,
                                                                 units=units_to_close, side=closeside, type="market")
                                        ordercomment = "Closed %04d at %.4f" % (units_to_close,  res['price'])
                                    except Exception as e:
                                        ordercomment = "exception when trying to create reducing order : %s" %e
                                    sleep_seconds = 1  # be quick to follow up after order

            if ordercomment!="":
                print("%s %s") % (instrumentname1,ordercomment)
        #be more alert if we are close to a trigger
        sleep_seconds = max(1, min(robot_margin_closeout_pct - robot_mcpbuytrigger,
                                   robot_mcpselltrigger - robot_margin_closeout_pct))
    except Exception as e:
        ordercomment = "%s - exception occoured (%s)" % (ordercomment, str(e))

    ts = datetime.datetime.now().strftime('%H:%M:%S')
    if abs(last_robot_NAV - robot_NAV) > 1 or ordercomment <> "":
        account_size_usd=0
        positions = oanda.get_positions(robot_accountid)['positions'] #in usd
        largest_instrument=""
        largest_position_usd=0
        for position in positions:
            instrument=position['instrument']
            units=position['units']
            position_size_usd=0
            if instrument[:3]=="USD":
                account_size_usd+=units
                position_size_usd=units
            else:
                bid = oanda.get_prices(instruments=instrument)['prices'][0]['bid']
                position_size_usd=bid*units
                account_size_usd +=position_size_usd
            if position_size_usd>largest_position_usd:
                largest_position_usd=account_size_usd
                largest_instrument=instrument
        if largest_instrument=="":
            largest_instrument="EUR_USD"#avoid crash if no positions
        position_size_eur=account_size_usd/eur_usd_bid
        largest_position_eur=largest_position_usd / eur_usd_bid
        largest_postion_bid = oanda.get_prices(instruments=largest_instrument)['prices'][0]['bid']
        largest_postion_ask = oanda.get_prices(instruments=largest_instrument)['prices'][0]['ask']
        largest_position_spread = largest_postion_ask-largest_postion_bid
        print("%.2f %7.0f %.2f %.2f %.4f %.2f %.2f %.0f %s %s %s" % (
            robot_NAV,position_size_eur, robot_margin_closeout_pct, robot_margin_used, largest_position_spread, largest_postion_bid, largest_postion_ask,
            largest_position_eur, largest_instrument,ordercomment,ts))
        last_robot_NAV = robot_NAV

print("%s V0.001 ended" % program_name)

