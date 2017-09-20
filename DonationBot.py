import asyncio
import discord
import re
import time
import os
import configparser
import traceback
import MySQLdb
import datetime
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

## Get configuration from ini file
## No validation on its presence, so make sure these are present
config = configparser.RawConfigParser()
config.read('config.ini')
# - discord config
discord_user = config.get('discord', 'discord.user')
discord_pass = config.get('discord', 'discord.pass')
discord_server = config.get('discord', 'discord.serverid')
# - db config
sql_user = config.get('sql', 'sql.user')
sql_pass = config.get('sql', 'sql.pass')
sql_host = config.get('sql', 'sql.host')
sql_port = int(config.get('sql', 'sql.port'))
sql_db = config.get('sql', 'sql.db')
# - admin roles
roles_admin = config.get('admin', 'admin.roles').split(',')
super_admin = config.get('admin', 'admin.super').split(',')
# - donor role
donor_role = config.get('donor', 'donor.role')
# - bot settings
bot_debug = int(config.get('bot', 'bot.debug'))

# Start discord client
client = discord.Client()

## Uncomment below if you want announcements on who joins the server.
@client.async_event
def on_member_join(member):
    server = member.server
    fmt = 'Welcome {0.mention} to {1.name}!'
    # yield from client.send_message(server, fmt.format(member, server))
    # yield from client.send_message(discord.utils.find(lambda u: u.id == member.id, client.get_all_members()), helpmsg)
    # print('Sent intro message to '+ member.name)

@client.async_event
def on_ready():
    print('Connected! Ready to notify.')
    print('Username: ' + client.user.name)
    print('ID: ' + client.user.id)
    print('--Server List--')
    for server in client.servers:
        discord_server = server.id
        print(server.id + ': ' + server.name)
    

# --- Help messages ---
# The !help message for normal users
helpmsg = "\n\
Commands\n\
\n\
`!donor expire` if you have donated and are process by the system you can check until when you're a donor. Donate before the expiration date to continue your subscription. \n\
`!donor contrib` list all the months added in your name. \n\
"

# The !help message for admin users
helpamsg = "\n\n\
Admin commands\n\
\n\
`!donor add {user} {#months}` this will add a new user and a contribution or add a contribution and update the valid date on a donor.\n\
If today is not the 25th of the month or later, it will count as a donation for this month, if it is made after it will start counting from next month.\n\
e.g. if today is the 19th of september and you type `!donor add nickname 1` it will count towards the end of september. If it is the 25th of September it will count towards the end of October.\n\
`!donor expire {user}` find out the expiration for a user. \n\
`!donor contrib {user}` find out all months added to a user with the date.\n\
`!donor subs` will list all users in the database with a valid subscription and when it runs out.\n\
`!donor expiration` will list all users whose subscription runs out at the end of this month.\n\
"
# The message shown for unprivileged users
helpsamsg = "\n\n\
Super Admin commands\n\
\n\
`!donor clean` remove all the Donor role from expired contributors.\n\
"
# --- End help messages ---

@client.async_event
def on_message(message):
    if message.channel.is_private:
        if '!donor help' == message.content[0:11]:
            returnmsg = helpmsg
            if roleacc(message, 'super') or roleacc(message, 'admin'):
                returnmsg += helpamsg
            if roleacc(message, 'super'):
                returnmsg += helpsamsg
            yield from client.send_message(message.channel, returnmsg)
    if '!donor add' == message.content[0:10] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        yield from donor_add(message)
    if '!donor expiration' == message.content[0:17] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        yield from donor_expiration(message)
    if '!donor subs' == message.content[0:11] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        yield from donor_subs(message)
    if '!donor clean' == message.content[0:12] and roleacc(message, 'super'):
        yield from donor_clean(message)
    if '!donor contrib' == message.content[0:14]:
        yield from donor_contrib(message)
    if '!donor expire' == message.content[0:13]:
        yield from donor_expire(message)

##################################################

# -- Donor functions --
# Helper function to get all active subscribers
def donor_subs(message):
    # Current time
    now = int(time.time())
    # verify existence of discordid on the server
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate > {} ORDER BY name;".format(now))
    data = c.fetchall()
    c.close()
    db_close(db)

    # Build the list of subs
    msg = ''
    msg += 'Active subscribers\n'
    msg += '\n'
    msg += 'Name'.ljust(20) + 'Date\n'
    msg += '----------------------------\n'
    for i, d in enumerate(data):
        msg += str(d[1]).ljust(20) + str(datetime.date.fromtimestamp(int(d[3]))) + '\n'
    
    yield from client.send_message(message.author, '```' + msg[:1994] + '```')
    if len(msg) >= 1994:
        for i in range(1, round(len(msg)/1994) ):
            c1 = '```'+ msg[i*1994:(i+1)*1994] + '```'
            yield from client.send_message(message.author, c1)

# Helper function to check your expiring members' subs
def donor_expiration(message):
    # Get the last day of this month.
    d_valid = datetime.date.fromtimestamp(int(time.time()))
    d_new_valid = d_valid + relativedelta(day=1, months=+1, days=-1)
    next_month = int(time.mktime(d_new_valid.timetuple()))
    # verify existence of discordid on the server
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate = {} ORDER BY name;".format(next_month))
    data = c.fetchall()
    c.close()
    db_close(db)

    # Build the list of expiring subs
    msg = ''
    msg += 'The following members\' subscription will expire at the end of this month\n'
    msg += '\n'
    msg += 'name\n'
    msg += '----\n'
    for i, d in enumerate(data):
        
        msg += str(d[1]).ljust(20) + '\n'

    yield from client.send_message(message.author, '```' + msg[:1994] + '```')
    if len(msg) >= 1994:
        for i in range(1, round(len(msg)/1994) ):
            c1 = '```'+ msg[i*1994:(i+1)*1994] + '```'
            yield from client.send_message(message.author, c1)
            
# Helper function to remove roles from expired subscriptions
def donor_clean(message):
    current_date = int(time.time())

    # verify existence of discordid on the server
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate < {} ORDER BY name;".format(current_date))
    data = c.fetchall()
    c.close()
    db_close(db)

    msg = ''
    for i, d in enumerate(data):
        #0=discord_id,1=name,2=startdate,3=validdate
        if bot_debug == 1:
            msg += 'Debug: Member {} should be removed now'.format(d[1])
        else:
            # lookup the userid, a bit clunky but fastest way.
            for member in server.members:
                if member.id == d[0]:
                   role = discord.utils.get(server.roles, name=donor_role)
                   yield from client.remove_roles(member, role)
                   msg += '{} removed from {}\n'.format(member.name, donor_role)
                   break

    yield from client.send_message(message.author, '```' + msg[:1994] + '```')
    if len(msg) >= 1994:
        for i in range(1, round(len(msg)/1994) ):
            c1 = '```'+ msg[i*1994:(i+1)*1994] + '```'
            yield from client.send_message(message.author, c1)

# Helper function to check contributions
def donor_contrib(message):
    server = client.get_server(discord_server)
    # Get all parameters
    smsg = message.content.lower().split()
    if len(smsg) == 3:
        # Only admins can pass parameters to this function.
        if (roleacc(message, 'super') or roleacc(message, 'admin')):
            user = smsg[2]
            discordid = None
            discordname = ""
            # lookup the userid, a bit clunky but fastest way.
            for member in server.members:
                if user_lookup(member, user):
                   discordid = member.id
                   discordname = member.name
                   break
            if discordid is not None:
                # verify existence of rol on the server
                db = db_connect()
                c = db.cursor()
                c.execute("SELECT * FROM donor WHERE discord_id = '{}';".format(discordid))
                row = c.fetchone()
                c.close()
                db_close(db)
                if row is None:
                    yield from client.send_message(message.channel, "Contribution information for member `{}` can't be found in the system.".format(discordname))                
                else:
                    startdate = str(datetime.date.fromtimestamp(int(row[2])))
                    validdate = str(datetime.date.fromtimestamp(int(row[3])))
                    # verify existence of rol on the server
                    db = db_connect()
                    c = db.cursor()
                    c.execute("SELECT * FROM donation WHERE discord_id = '{}' ORDER BY id DESC;".format(discordid))
                    data = c.fetchall()
                    c.close()
                    db_close(db)

                    msg = '```'
                    msg += 'Contribution information for {}\n'.format(discordname)
                    msg += '----------------------\n'
                    msg += 'Added date:'.ljust(12) + startdate + '\n'
                    msg += 'Valid date:'.ljust(12) + validdate + '\n'
                    msg += '\n'
                    msg += 'months'.ljust(12) + 'date\n'
                    msg += '----------------------\n'
                    for i, d in enumerate(data):
                        msg += str(d[2]).ljust(12) + str(datetime.date.fromtimestamp(int(d[3]))) + '\n'
                    msg += '```'
                    
                    yield from client.send_message(message.channel, msg)
            else:
                yield from client.send_message(message.channel, "Unfortunately member `{}` can't be found in the system, check the spelling or try finding it by id.".format(user))
        else:
            yield from client.send_message(message.channel, "You don't have permissions to lookup other members' expiration date.")
    else: 
      discordid = message.author.id
      # verify existence of discordid on the server
      db = db_connect()
      c = db.cursor()
      c.execute("SELECT * FROM donation WHERE discord_id = '{}' ORDER BY id DESC;".format(discordid))
      data = c.fetchall()
      rc = c.rowcount
      c.close()
      db_close(db)

      msg = '```'
      if rc > 0:
          msg += 'months'.ljust(12) + 'date\n'
          msg += '----------------------\n'
          for i, d in enumerate(data):
              msg += str(d[2]).ljust(12) + str(datetime.date.fromtimestamp(int(d[3]))) + '\n'
      else:
          msg+= 'There is no contribution information for your user'
      msg += '```'
      
      yield from client.send_message(message.channel, msg)

# Helper function to check your donation expiration
def donor_expire(message):
    server = client.get_server(discord_server)
    msg = message.content.lower().split()
    if len(msg) == 3:
        if (roleacc(message, 'super') or roleacc(message, 'admin')):
            user = msg[2]
            discordid = None
            discordname = ""
            # lookup the userid, a bit clunky but fastest way.
            for member in server.members:
                if user_lookup(member, user):
                   discordid = member.id
                   discordname = member.name
                   break
            if discordid is not None:
                # verify existence of rol on the server
                db = db_connect()
                c = db.cursor()
                c.execute("SELECT * FROM donor WHERE discord_id = '{}';".format(discordid))
                row = c.fetchone()
                c.close()
                db_close(db)
                if row is not None:
                    validity = int(row[3])
                    yield from client.send_message(message.channel, "The subscription for `{}` will expire on `{}`.".format(discordname, str(datetime.date.fromtimestamp(validity))))
                else:
                    yield from client.send_message(message.channel, "Unfortunately member `{}` can't be found in the system, check the spelling or try finding it by id.".format(user))
        else:
            yield from client.send_message(message.channel, "You don't have permissions to lookup other members' expiration date.")
    else: 
      discordid = message.author.id
      # verify existence of rol on the server
      db = db_connect()
      c = db.cursor()
      c.execute("SELECT * FROM donor WHERE discord_id = '{}';".format(discordid))
      row = c.fetchone()
      c.close()
      db_close(db)

      # If the donor exists, add a payment & update the validity
      if row is not None:
          validity = int(row[3])
          yield from client.send_message(message.channel, "Your subscription will expire on `{}`.".format(str(datetime.date.fromtimestamp(validity))))
      else:
          yield from client.send_message(message.channel, "Unfortunately you are not known in the system, please contact a moderator if you have donated.")

# Function to add monitored channels to the database
def donor_add(message):
    server = client.get_server(discord_server)
    msg = message.content.lower().split()
    if len(msg) < 4:
        yield from client.send_message(message.channel, "You are missing a parameter to the command, please verify and retry.")
    else:
        # instance of server for later use
        server = client.get_server(discord_server)
        # We expect these values.
        user = msg[2]
        month = msg[3]

        discordid = None
        discordname = ""
        discordmember = None
        # lookup the userid, a bit clunky but fastest way.
        for member in server.members:
            if user_lookup(member, user):
               discordid = member.id
               discordname = member.name
               discordmember = member
               break
        if discordid is not None:
            # verify existence of rol on the server
            db = db_connect()
            c = db.cursor()
            c.execute("SELECT * FROM donor WHERE discord_id = '{}';".format(discordid))
            row = c.fetchone()
            c.close()
            db_close(db)

            # If the donor exists, add a payment & update the validity
            if row is not None:
                created = int(time.time())
                old_valid = int(row[3])
                valid = new_valid_time(old_valid, month)
                
                db = db_connect()
                c = db.cursor()
                donationadded = False
                try:
                    c.execute("""INSERT INTO donation (discord_id, amt, donationdate) VALUES (%s, %s, %s)""", (discordid, month, created))
                    db.commit()
                    donationadded = True
                except MySQLdb.Error as e:
                    db.rollback()
                    print(str(e))
                db_close(db)

                if donationadded:
                    db = db_connect()
                    c = db.cursor()
                    try:
                        c.execute ("""UPDATE donor SET validdate=%s WHERE discord_id=%s""", (valid, discordid))
                        db.commit() 
                    except:
                        db.rollback()
                    db_close(db)
                    if old_valid < created:
                        if bot_debug == 1:
                            print('Debug: Member {} should be added now'.format(discordname))
                        else:
                            role = discord.utils.get(server.roles, name=donor_role)
                            yield from client.add_roles(discordmember, role)
                    yield from client.send_message(message.channel, "Added a contribution for `{} months` for user `{}` it will expire at `{}`".format(user, discordname, str(datetime.date.fromtimestamp(valid))))
                else:
                    yield from client.send_message(message.channel, "There was a problem adding a donation for donor `{}`. Contact an admin if this problem persists".format(discordname))
            # If the donor doesn't exist, create a new entry for the donors, calculate the validity & add a payment
            else:
                created = int(time.time())
                valid = new_valid_time(created, month)

                db = db_connect()
                c = db.cursor()
                donoradded = False
                try:
                    c.execute("""INSERT INTO donor (discord_id, name, startdate, validdate) VALUES (%s, %s, %s, %s)""", (discordid, discordname, created, valid))
                    db.commit()
                    donoradded = True
                except MySQLdb.Error as e:
                    db.rollback()
                    print(str(e))

                db_close(db)
                
                if donoradded:
                    db = db_connect()
                    c = db.cursor()
                    donationadded = False
                    try:
                        c.execute("""INSERT INTO donation (discord_id, amt, donationdate) VALUES (%s, %s, %s)""", (discordid, month, created))
                        db.commit()
                        donationadded = True
                    except MySQLdb.Error as e:
                        db.rollback()
                        print(str(e))

                    db_close(db)

                    if donationadded:
                        if bot_debug == 1:
                            print('Debug: Member {} should be added now'.format(discordname))
                        else:
                            role = discord.utils.get(server.roles, name=donor_role)
                            yield from client.add_roles(discordmember, role)
                        yield from client.send_message(message.channel, "Added donor `{}` to the database with a first contribution for `{} months`".format(discordname, month))
                    else:
                        yield from client.send_message(message.channel, "There was a problem adding a donation for donor `{}`. Contact an admin if this problem persists".format(user))
                else:
                    yield from client.send_message(message.channel, "An error occurred adding donor `{}` to the database, try again later or contact and administrator".format(user))
        else:
            yield from client.send_message(message.channel, "An error occurred trying to add donor `{}` to the database".format(user))

# -- End Donor functions

# --- Helper Methods ---
# Helper function to determine the validity
def new_valid_time(valid, m):
    # convert month to int, we jump one month ahead to get the last month 
    m = int(m) + 1
    # Keep the unix timestamps for comparison
    now = int(time.time())
    # Convert to datetime objects for relative adding
    d_now = datetime.date.fromtimestamp(now)
    d_valid = datetime.date.fromtimestamp(valid)
    # if m = 1 then trigger the expire function
    if valid > now:
        # Add months
        d_new_valid = d_valid + relativedelta(day=1,months=+m,days=-1)

        # get unixtimestamp
        t_new_valid = int(time.mktime(d_new_valid.timetuple()))
        
        
        return t_new_valid
    else:
        # if the day of the month is lower than 25, it will count for this month
        if d_now.day < 25:
            m = m - 1
        d_new_valid = d_now + relativedelta(day=1,months=+m,days=-1)

        # get unixtimestamp
        t_new_valid = int(time.mktime(d_new_valid.timetuple()))

        return t_new_valid

# Helper function to check permissions
def roleacc(message, group):
    # distinguish whether the user is high privileged than @everyone
    stopUnauth = False
    # in PM determine the user roles from the server settings.
    if message.author.__class__.__name__ ==  'User':
        msrv = client.get_server(discord_server)
        usr = msrv.get_member(message.author.id)
    # in channel message, the Member object is available directly
    elif message.author.__class__.__name__ ==  'Member':
        usr = message.author
    else:
        return stopUnauth
    # Superadmin check
    if group == 'super':
        global super_admin
        # Cycle through the roles on the user object
        for sid in super_admin:
            if usr.id == sid:
                stopUnauth = True
                break        
        return stopUnauth
    elif group == 'admin':    
        try:
            getattr(usr, 'roles') 
        except AttributeError:
            print("-- Debug info -- ")
            print("type: " + message.type.name)
            print("channel: " + message.channel.name)
            print("bot: " + str(message.author.bot))
            return stopUnauth
        
            global roles_admin
            # Cycle through the roles on the user object
            for role in roles_admin:
               if role.id in roles_list.keys() and roles_list[role.id][group] == 1:
                 stopUnauth = True
                 break         
            return stopUnauth
    return stopUnauth

def user_lookup(member, user):

    return str(member.name).lower() == user.lower() or str(member.name + '#' + member.discriminator).lower() == user or member.id == user or str(member.nick).lower() == user.lower()

# --- db functions ---
# Helper function to execute a query and return the results in a list object
def db_connect():
    # Setup the db connection with the global params
    connection = MySQLdb.connect(host=sql_host, port=sql_port, user=sql_user, passwd=sql_pass, db=sql_db)
    return connection
    
def db_close(connection):
    connection.close()
# --- End db functions ---
# --- End helper Methods ---


loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(client.login(discord_user, discord_pass))
    loop.run_until_complete(client.connect())
except Exception:
    loop.run_until_complete(client.close())
finally:
    loop.close()
