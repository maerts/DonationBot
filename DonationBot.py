import asyncio
import discord
import re
import time
import os
import configparser
import traceback
import MySQLdb
import datetime
import gc
import traceback
import sys
import functools
import random
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from time import sleep

## Get configuration from ini file
## No validation on its presence, so make sure these are present
config = configparser.RawConfigParser()
config.read('config.ini')
# - discord config
discord_user = config.get('discord', 'discord.user')
discord_pass = config.get('discord', 'discord.pass')
discord_server = int(config.get('discord', 'discord.serverid'))
discord_bothash = config.get('discord', 'discord.bothash')
discord_bot = int(config.get('discord', 'discord.bot'))
# - db config
sql_user = config.get('sql', 'sql.user')
sql_pass = config.get('sql', 'sql.pass')
sql_host = config.get('sql', 'sql.host')
sql_port = int(config.get('sql', 'sql.port'))
sql_db = config.get('sql', 'sql.db')
# - admin roles
roles_admin = config.get('admin', 'admin.roles').split(',')
super_admin = config.get('admin', 'admin.super').split(',')
channels_admin = config.get('admin', 'admin.channels').split(',')
# - donor role
donor_role = config.get('donor', 'donor.role')
donor_expiremsg = config.get('donor', 'donor.expiremsg')
donor_enablewelcome = int(config.get('donor', 'donor.enablewelcome'))
donor_newmsg = config.get('donor', 'donor.newmsg')
donor_botroom = config.get('donor', 'donor.botroom')
donor_welcomeroom = config.get('donor', 'donor.welcomeroom')
donor_chatmods = config.get('donor', 'donor.chatmods')
# - bot settings
bot_debug = int(config.get('bot', 'bot.debug'))

# Start discord client
client = discord.Client()

## Uncomment below if you want announcements on who joins the server.
@client.event
async def on_member_join(member):
    server = member.server
    fmt = 'Welcome {0.mention} to {1.name}!'
    # await client.send_message(server, fmt.format(member, server))
    # await client.send_message(discord.utils.find(lambda u: u.id == member.id, client.get_all_members()), helpmsg)
    # print('Sent intro message to '+ member.name)

@client.event
async def on_ready():
    watchdog('Connected! Ready to notify.')
    watchdog('Username: ' + client.user.name)
    watchdog('ID: ' + str(client.user.id))
    watchdog('--Server List--')
    for server in client.guilds:
        discord_server = server.id
        watchdog(str(server.id) + ': ' + server.name)
        for role in server.roles:
            watchdog(role.name + ': ' + str(role.id))


# --- Help messages ---
# The .help message for normal users
helpmsg = "\n\
Commands\n\
\n\
`.donor expire` if you have donated and are process by the system you can check until when you're a donor. Donate before the expiration date to continue your subscription. \n\
`.donor contrib` list all the months added in your name. \n\
"

# The .help message for admin users
helpamsg = "\n\n\
Admin commands\n\
\n\
`.donor add {user} {#months}` this will add a new user and a contribution or add a contribution and update the valid date on a donor.\n\
If today is not the 25th of the month or later, it will count as a donation for this month, if it is made after it will start counting from next month.\n\
e.g. if today is the 19th of september and you type `.donor add nickname 1` it will count towards the end of september. If it is the 25th of September it will count towards the end of October.\n\
`.donor remove {user} {#months}` removes months from a given users.\n\
`.donor expire {user}` find out the expiration for a user. \n\
`.donor contrib {user}` find out all months added to a user with the date.\n\
`.donor change {olduser} {newuser}` update an existing user to a new user.\n\
`.donor subs` will list all users in the database with a valid subscription and when it runs out.\n\
`.donor stats` will give a short list with information about donor numbers.\n\
`.donor expiration` will list all users whose subscription runs out at the end of this month.\n\
`.donor freeloader` will list all users whose subscription has run out but that still have the Donor role.\n\
`.note add {user} {note}` will add a note to a user that only mods & admins can access.\n\
`.note del {id}` will delete a note from the database.\n\
`.note list {user}` will list all notes or the notes for a specific user when provided.\n\
"
# The message shown for unprivileged users
helpsamsg = "\n\n\
Super Admin commands\n\
\n\
`.donor clean` remove all the Donor role from expired contributors.\n\
`.donor expiration notify` it does the same as `.donor expiration` with the addition of sending all expirees a DM about their expiration.\n\
"
# --- End help messages ---

@client.event
async def on_message(message):
    if '.donor help' == message.content[0:11]:
        returnmsg = helpmsg
        if roleacc(message, 'super') or roleacc(message, 'admin'):
            returnmsg += helpamsg
        if roleacc(message, 'super'):
            returnmsg += helpsamsg
        if str(message.channel.type) == 'text':
            if roleacc(message, 'super') or roleacc(message, 'admin'):
                server = client.get_guild(discord_server)
                usr = server.get_member(message.author.id)
                await usr.send(returnmsg)
            else:
                channel = message.channel
                await channel.send(returnmsg)
        else:
            server = client.get_guild(discord_server)
            usr = server.get_member(message.author.id)
            await usr.send(returnmsg)

    if '.userid' == message.content[0:7] and (roleacc(message, 'super') or roleacc(message, 'admin')) and str(message.channel.type) == 'text' and message.channel.name in channels_admin:
        await user_get(message)
    if '.donor add' == message.content[0:10] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await donor_add(message)
    if '.donor remove' == message.content[0:13] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await donor_remove(message)
    if '.donor expiration' == message.content[0:17] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await donor_expiration(message)
    if '.donor subs' == message.content[0:11] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await donor_subs(message)
    if '.donor clean' == message.content[0:12] and roleacc(message, 'super'):
        await donor_clean(message)
    if '.donor contrib' == message.content[0:14]:
        await donor_contrib(message)
    if '.donor change' == message.content[0:13] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await donor_change(message)
    if '.donor expire' == message.content[0:13]:
        await donor_expire(message)
    if '.donor freeloader' == message.content[0:17] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await donor_freeloader(message)
    if '.donor stats' == message.content[0:17] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await donor_stats(message)
    if '.note add' == message.content[0:9] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await note_add(message)
    if '.note del' == message.content[0:9] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await note_del(message)
    if '.note list' == message.content[0:10] and (roleacc(message, 'super') or roleacc(message, 'admin')):
        await note_list(message)


##################################################
# -- Note functions --
# Helper function to check your donation expiration
async def user_get(message):
    server = client.get_guild(discord_server)
    msg = message.content.lower().split()
    channel = message.channel
    if len(msg) < 2:
        await channel.send("Yes, yes you are!")
    else:
        user = " ".join(msg[1:])
        watchdog(str(user))
        discordmember = None
        # lookup the userid, a bit clunky but fastest way.
        count = 0
        duplicatemembers = []
        for member in server.members:
            if user_lookup(member, user):
               discordmember = member
               count = count + 1
               duplicatemembers.append(member)
        if discordmember is not None:
            if count > 1:
                em = discord.Embed(title="Multiple users found", description="I have found multiple users with this name")
                await channel.send(embed=em)
                for i, member in enumerate(duplicatemembers):
                    em = discord.Embed()
                    em.set_author(name=member.name, icon_url=member.avatar_url)
                    em.add_field(name="User ID:", value=member.id, inline=False)
                    em.add_field(name="Current Username:", value=member.display_name, inline=False)
                    em.add_field(name="Current Nickname:", value=member.nick, inline=False)
                    em.add_field(name="Unique:", value=member.name + "#" + member.discriminator, inline=False)
                    em.add_field(name="User Since:", value=member.created_at, inline=False)
                    em.add_field(name="Highest role:", value=member.top_role.name, inline=False)
                    await channel.send(embed=em)
            else:
                member = discordmember
                em = discord.Embed()
                em.set_author(name=member.name, icon_url=member.avatar_url)
                em.add_field(name="User ID:", value=member.id, inline=False)
                em.add_field(name="Current Username:", value=member.display_name, inline=False)
                em.add_field(name="Current Nickname:", value=member.nick, inline=False)
                em.add_field(name="Unique:", value=member.name + "#" + member.discriminator, inline=False)
                em.add_field(name="User Since:", value=member.created_at, inline=False)
                em.add_field(name="Highest role:", value=member.top_role.name, inline=False)
                await channel.send(embed=em)
        else:
            sugg = []
            for member in server.members:
                dn = levenshtein(member.display_name.lower(), user.lower()) if member.display_name is not None else 10
                ni = levenshtein(member.nick.lower(), user.lower()) if member.nick is not None else 10
                na = levenshtein(member.name.lower(), user.lower()) if member.name is not None else 10
                nd = levenshtein(member.name.lower()+ "#" + str(member.discriminator), user.lower()) if member.name is not None else 10
                if dn < 3:
                    sugg.append(member.display_name.lower())
                    continue
                if ni < 3:
                    sugg.append(member.nick.lower())
                    continue
                if na < 3:
                    sugg.append(member.name.lower())
                    continue
                if nd < 3:
                    sugg.append(member.name.lower()+ "#" + str(member.discriminator))
                    continue

            if len(sugg) == 0:
                em = discord.Embed()
                em.add_field(name="User {} not found".format(user), value="Please make sure you wrote the right id, name, nickname, unique name or display name.", inline=False)
                await channel.send(embed=em)
            else:
                em = discord.Embed()
                em.add_field(name="User {} not found".format(user), value="Could it be one of the following? `{}`".format(', '.join(sugg)), inline=False)
                await channel.send(embed=em)

##################################################
# -- Note functions --
# Helper function to check your donation expiration
async def note_add(message):
    server = client.get_guild(discord_server)
    msg = message.content.lower().split()
    if len(msg) > 3:
        db = db_connect()
        c = db.cursor()
        now = int(time.time())
        user = msg[2]
        note = msg[3:]
        discordid = None
        discordname = ""
        # lookup the userid, a bit clunky but fastest way.
        count = 0
        duplicatemembers = []
        for member in server.members:
            if user_lookup(member, user):
               discordid = str(member.id)
               discordname = member.name
               count = count + 1
               duplicatemembers.append(member)
        if count > 1:
            dup_msg = "I have discovered multiple users with this name.\nVerify and try it with the discriminator or id.\n"
            dup_msg += "\n".rjust(35, '-')
            for i, member in enumerate(duplicatemembers):
                dup_msg += str(i + 1) + ". **" + member.name + "#" + member.discriminator + "** (" + member.id + ")\n"
            channel = message.channel
            await channel.send(dup_msg)
        else:
            if discordid is not None:
                # verify existence of rol on the server
                success = False
                try:

                    c.execute("""INSERT INTO notes (discord_id, reporter_id, startdate, note) VALUES (%s, %s, %s, %s)""", (discordid, message.author.id, now, " ".join(note)))
                    db.commit()
                    success = True
                except MySQLdb.Error as e:
                    db.rollback()
                    watchdog("INSERT ERROR: " + str(e))
                c.close()
                db_close(db)
                channel = message.channel
                if success:
                    await channel.send("A note has been recorded for `{}`.".format(discordname))
                else:
                    await channel.send("Something went wrong trying to add a note for `{}`.".format(discordname))
    else:
        channel = message.channel
        await channel.send("Wrong usage! `.note add user this guy is awesome`")

async def note_del(message):
    server = client.get_guild(discord_server)
    msg = message.content.lower().split()
    channel = message.channel
    if len(msg) == 3:
        db = db_connect()
        c = db.cursor()
        nid = int(msg[2])

        # verify existence of rol on the server
        deleted = 0
        try:
            c.execute("""DELETE FROM notes WHERE nid=%s""", (nid,))
            deleted = c.rowcount
            db.commit()
        except MySQLdb.Error as e:
            db.rollback()
            watchdog(str(e))
        c.close()
        db_close(db)
        if deleted > 0:
            await channel.send("Note with id `{}` has been removed.".format(nid))
        else:
            await channel.send("Something went wrong trying to delete note with id `{}`.".format(nid))
    else:
        await channel.send("Wrong usage! `.note del 123` where 123 is the note number")

async def note_list(message):
    server = client.get_guild(discord_server)
    msg = message.content.lower().split()
    channel = message.channel
    if len(msg) >= 3:
        db = db_connect()
        c = db.cursor()
        now = int(time.time())
        user = msg[2]
        note = msg[3:]
        discordid = None
        discordname = ""
        # lookup the userid, a bit clunky but fastest way.
        count = 0
        duplicatemembers = []
        for member in server.members:
            if user_lookup(member, user):
               discordid = str(member.id)
               discordname = member.name
               count = count + 1
               duplicatemembers.append(member)
        if count > 1:
            dup_msg = "I have discovered multiple users with this name.\nVerify and try it with the discriminator or id.\n"
            dup_msg += "\n".rjust(35, '-')
            for i, member in enumerate(duplicatemembers):
                dup_msg += str(i + 1) + ". **" + member.name + "#" + member.discriminator + "** (" + member.id + ")\n"
            await channel.send(dup_msg)
        else:
            if discordid is not None:
                # verify existence of rol on the server
                c.execute("SELECT * FROM notes WHERE discord_id = '{}' ORDER BY nid ASC;".format(discordid))
                data = c.fetchall()
                c.close()
                db_close(db)

                msg = '```'
                msg += 'Notes for {}\n'.format(discordname)
                msg += '\n'.rjust(50, '-')
                msg += 'nid'.ljust(5) + 'date'.ljust(15) + 'by'.ljust(20) +'note\n'
                msg += '\n'.rjust(50, '-')
                for i, d in enumerate(data):
                    by_member = "unknown"
                    for member in server.members:
                        if user_lookup(member, str(d[2])):
                            by_member = member.name
                    d_nid = str(d[0]).ljust(5)
                    d_date = str(datetime.date.fromtimestamp(int(d[3]))).ljust(15)
                    d_by = by_member.ljust(20)
                    msg += d_nid + d_date + d_by + d[4].decode('ascii') + '\n'
                msg += '```'
                return_channel = message.channel
                if return_channel.name not in channels_admin and str(message.channel.type) == 'text':
                    return_channel = server.get_member(message.author.id)
                await return_channel.send(msg)
    else:
        db = db_connect()
        c = db.cursor()
        now = int(time.time())
        # verify existence of rol on the server
        c.execute("SELECT * FROM notes ORDER BY nid ASC;")
        data = c.fetchall()
        c.close()
        db_close(db)

        msg = '```'
        msg += 'All notes\n'
        msg += '\n'.rjust(80, '-')
        msg += 'nid'.ljust(5) + 'date'.ljust(15) + 'for'.ljust(20) + 'by'.ljust(20) +'note\n'
        msg += '\n'.rjust(80, '-')
        for i, d in enumerate(data):
            by_member = "unknown"
            for member in server.members:
                if user_lookup(member, str(d[2])):
                    by_member = member.name
            for_member = ""
            for member in server.members:
                if user_lookup(member, str(d[1])):
                    for_member = member.name
            d_nid = str(d[0]).ljust(5)
            d_date = str(datetime.date.fromtimestamp(int(d[3]))).ljust(15)
            d_for = for_member.ljust(20)
            d_by = by_member.ljust(20)
            msg += d_nid + d_date + d_for + d_by + d[4].decode('ascii') + '\n'
        msg += '```'
        return_channel = message.channel
        if return_channel.name not in channels_admin and str(message.channel.type) == 'text':
            return_channel = server.get_member(message.author.id)
        await return_channel.send(msg)

# -- End note functions --


# -- Donor functions --
# Helper function to get all active subscribers
async def donor_stats(message):
    # Current time
    now = int(time.time())
    mod_ids = get_management()
    print(mod_ids)
    # get all donors with a valid date higher than now
    db = db_connect()
    c = db.cursor()
    query = "SELECT CONCAT(MONTHNAME(FROM_UNIXTIME(validdate)), ' ', YEAR(FROM_UNIXTIME(validdate))) as short_notation, count(1) FROM donor GROUP BY short_notation, validdate HAVING validdate > {} ORDER BY validdate ASC;".format(now) # AND discord_id NOT IN ('{}')  | , "', '".join(mod_ids)
    c.execute(query)
    print(query);
    data = c.fetchall()
    c.close()
    db_close(db)

    forecast = {}
    for i, d in enumerate(data):
        for key in forecast.keys():
            tmp = forecast[key]
            forecast[key] = tmp + int(d[1])
        forecast[str(d[0])] = int(d[1])
    s_forecast = [(k, forecast[k]) for k in sorted(forecast, key=forecast.get, reverse=True)]


    # get the mount of donors.
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT count(1) FROM donor WHERE validdate > {};".format(now))
    amount = c.fetchone()
    c.close()
    db_close(db)

    # Build the list of subs
    msg = '```'
    msg += 'Active subscribers ({})\n'.format(amount[0])
    msg += '\n'.rjust(50, '-')
    msg += 'Forecast up to month\n'
    msg += '\n'.rjust(50, '-')
    for k, v in s_forecast:
        msg+= k.ljust(25) + str(v) + '\n'
    msg += '```'
    channel = message.channel
    await channel.send(msg)

# Helper function to get all active subscribers
async def donor_subs(message):
    server = client.get_guild(discord_server)
    # Current time
    now = int(time.time())
    # get all donors with a valid date higher than now
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate > {} ORDER BY validdate ASC, name;".format(now))
    data = c.fetchall()
    c.close()
    db_close(db)

    # get the mount of donors.
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT count(1) FROM donor WHERE validdate > {};".format(now))
    amount = c.fetchone()
    c.close()
    db_close(db)

    return_channel = server.get_member(message.author.id)

    # Build the list of subs
    msg = '```'
    msg += 'Active subscribers ({})\n'.format(amount[0])
    msg += '\n'
    msg += 'Name'.ljust(40) + 'Date'.ljust(20) + 'discord_id\n'
    msg += '\n'.rjust(95, '-')
    for i, d in enumerate(data):
        tmp = str(d[1]).ljust(40) + str(datetime.date.fromtimestamp(int(d[3]))).ljust(20) + str(d[0]) + '\n'
        if (len(tmp) + len(msg)) >  1997:
            msg += '```'
            await return_channel.send(msg)
            msg = '```'
        msg += tmp
    msg += '```'
    await return_channel.send(msg)

# Helper function to check your expiring members' subs
async def donor_freeloader(message):
    server = client.get_guild(discord_server)
    # Get the last day of this month.
    d_valid = int(time.time())
    # verify existence of discordid on the server
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate > {} ORDER BY name;".format(d_valid))
    data = c.fetchall()
    c.close()
    db_close(db)

    valid = []
    for i, d in enumerate(data):
        valid.append(str(d[0]))

    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate < {} ORDER BY name;".format(d_valid))
    data = c.fetchall()
    c.close()
    db_close(db)

    expired = {}
    for i, d in enumerate(data):
        expired[str(d[0])] = str(datetime.date.fromtimestamp(int(d[3])))

    return_channel = server.get_member(message.author.id)

    # Build the list of expiring subs
    msg = '```'
    counter = 0
    msg += 'The following members\' subscription has expired \n'
    msg += '\n'
    msg += 'name'.ljust(50) + 'expired'.ljust(15) + 'memberid\n'
    msg += ''.ljust(120, '-') + '\n'
    for member in server.members:
        if member.top_role.name == donor_role and member.id not in valid:
            counter = counter + 1
            expired_date = 'Not in bot'
            if member.id in expired.keys():
                expired_date = expired[member.id]
            name = str(member.name + '#' + member.discriminator)
            if member.name == '':
                name = str(member.id)
            tmp = str(name).ljust(50) + expired_date.ljust(15) + member.id + '\n'
            if (len(tmp) + len(msg)) >  1997:
                msg += '```'
                await return_channel.send(msg)
                msg = '```'
            msg += tmp
    msg += '```'
    await return_channel.send(msg)
    msg = "```A total of {} members have the donor status but aren't in the bot.```".format(str(counter))
    await return_channel.send(msg)


# Helper function to check your expiring members' subs
async def donor_expiration(message):
    server = client.get_guild(discord_server)
    msg = message.content.lower().split()
    notify_members = {}
    notify = False
    if len(msg) == 3 and msg[2] == 'notify':
        notify = True
    # Get the last day of this month.
    d_valid = datetime.date.fromtimestamp(int(time.time()))
    d_new_valid = d_valid + relativedelta(day=31)
    next_month = int(time.mktime(d_new_valid.timetuple()))
    # verify existence of discordid on the server
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate = {} ORDER BY name;".format(next_month))
    data = c.fetchall()
    c.close()
    db_close(db)

    return_channel = server.get_member(message.author.id)

    if notify:
        variable_set('notify_last_run', str(d_valid))
    counter = 0
    # Build the list of expiring subs
    msg = '```'
    msg += 'The following members\' subscription will expire at the end of this month\n'
    msg += '\n'
    msg += 'name'.ljust(35) + 'id\n'
    msg += '----\n'
    for i, d in enumerate(data):
        counter = counter + 1
        if notify:
            user = server.get_member(str(d[0])) #
            if user != None:
                notify_members[str(d[0])] = donor_expiremsg
            else:
                watchdog('Could not notify {}'.format(d[0]))
        tmp = str(d[1]).ljust(35) + str(d[0]) + '\n'
        if (len(tmp) + len(msg)) >  1997:
            msg += '```'
            await return_channel.send(msg)
            msg = '```'
        msg += tmp
    msg += '```'
    await return_channel.send(msg)
    msg = '```There are {} donors expiring at the end of the month.\nThe notify command has been last run at {}.```'.format(str(counter), str(variable_get('notify_last_run')))
    await return_channel.send(msg)
    if len(notify_members.keys()) > 0:
        try:
            asyncio.ensure_future(async_loop_send_messages(notify_members, 'txt'), loop=client.loop).add_done_callback(async_loop_complete_result)
        except Exception as exc:
            print(exc)

async def async_loop_send_messages(list, type):
    server = client.get_guild(discord_server)
    counter = 0

    return_channel = server.get_member(message.author.id)

    # watchdog(str(list))
    for key in list.keys():
        if counter != 0 and counter % 5 == 0:
            watchdog('sleep started')
            time.sleep(random.randint(3, 12))
            watchdog('sleep passed')
        counter = counter + 1
        val = list[key];
        try:
            usr = server.get_member(int(key))
            if type == 'emb':
                await usr.send(embed=val)
            else:
                await usr.send(val)
            watchdog('send message to {} of type {}'.format(usr.name, type))
        except Exception as exc:
            watchdog(str(exc))

def async_loop_complete_result(future):
    watchdog('Loop complete')


# Helper function to remove roles from expired subscriptions
async def donor_clean(message):
    current_date = int(time.time())
    server = client.get_guild(discord_server)
    return_channel = server.get_member(message.author.id)
    # verify existence of discordid on the server
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate < {} ORDER BY name;".format(current_date))
    data = c.fetchall()
    c.close()
    db_close(db)

    msg = '```'
    msg += 'Coroutine to remove the donor role from expired members\n'
    msg += ''.ljust(55, '-') + '\n'
    for i, d in enumerate(data):
        #0=discord_id,1=name,2=startdate,3=validdate
        tmp = ""
        # lookup the userid, a bit clunky but fastest way.
        for member in server.members:
            if member.id == d[0]:
                try:
                    role = discord.utils.get(server.roles, name=donor_role)
                    await member.remove_roles(role, reason="Donation status expired.")
                    tmp = '- {} removed from {}\n'.format(member.name, donor_role)
                    if bot_debug == 1:
                        tmp = 'Debug: Member {} should be removed now.\n'.format(d[1])
                except:
                    tmp = '# An error occured try to remove {} removed from {}\n'.format(member.name, donor_role)
                break
            if (len(tmp) + len(msg)) >  1997:
                msg += '```'
                await return_channel.send(msg)
                msg = '```'
            msg += tmp

    # verify existence of discordid on the server
    db = db_connect()
    c = db.cursor()
    c.execute("SELECT * FROM donor WHERE validdate > {} ORDER BY name;".format(current_date))
    data = c.fetchall()
    c.close()
    db_close(db)

    valid = []
    for i, d in enumerate(data):
        valid.append(str(d[0]))

    for member in server.members:
        if member.top_role.name == donor_role and member.id not in valid:
            watchdog(member.name + '#' + member.discriminator + ' - ' + member.id)
            try:
                role = discord.utils.get(server.roles, name=donor_role)
                await member.remove_roles(role, reason="Donation status expired.")
                tmp = '- {} removed from {}\n'.format(member.name + '#' + member.discriminator + ' (' + member.id + ')', donor_role)
                if bot_debug == 1:
                    watchdog('Debug: Member {} should be removed now.\n'.format(d[1]))
            except:
                tmp = '# An error occured try to remove {} removed from {}\n'.format(member.name, donor_role)
            if (len(tmp) + len(msg)) >  1997:
                msg += '```'
                await return_channel.send(msg)
                msg = '```'
            msg += tmp
    msg += '```'
    await return_channel.send(msg)

# Helper function to check contributions
async def donor_contrib(message):
    server = client.get_guild(discord_server)
    # Get all parameters
    channel = message.channel
    smsg = message.content.lower().split()
    if len(smsg) > 2:
        # Only admins can pass parameters to this function.
        if (roleacc(message, 'super') or roleacc(message, 'admin')):
            user = ' '.join(smsg[2:])
            discordid = None
            discordname = ""
            # lookup the userid, a bit clunky but fastest way.
            count = 0
            duplicatemembers = []
            for member in server.members:
                if user_lookup(member, user):
                   discordid = str(member.id)
                   discordname = member.name
                   count = count + 1
                   duplicatemembers.append(member)
            if count > 1:
                dup_msg = "I have discovered multiple users with this name.\nVerify and try it with the discriminator or id.\n"
                dup_msg += "\n".rjust(35, '-')
                for i, member in enumerate(duplicatemembers):
                    dup_msg += str(i + 1) + ". **" + member.name + "#" + member.discriminator + "** (" + member.id + ")\n"
                await channel.send(dup_msg)
            else:
                if discordid is not None:
                    # verify existence of rol on the server
                    db = db_connect()
                    c = db.cursor()
                    c.execute("SELECT * FROM donor WHERE discord_id = '{}';".format(discordid))
                    row = c.fetchone()
                    c.close()
                    db_close(db)
                    if row is None:
                        await channel.send("Contribution information for member `{}` can't be found in the system.".format(discordname))
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
                        await channel.send(msg)

                        return_channel = message.channel
                        if return_channel.name in channels_admin or str(message.channel.type) != 'text':
                            db = db_connect()
                            c = db.cursor()
                            c.execute("SELECT * FROM notes WHERE discord_id = '{}' ORDER BY nid ASC;".format(discordid))
                            data = c.fetchall()
                            c.close()
                            db_close(db)

                            note_cnt = 0
                            msg = '```'
                            msg += 'Notes for {}\n'.format(discordname)
                            msg += '\n'.rjust(50, '-')
                            msg += 'nid'.ljust(5) + 'date'.ljust(15) + 'by'.ljust(20) +'note\n'
                            msg += '\n'.rjust(50, '-')
                            for i, d in enumerate(data):
                                note_cnt = note_cnt + 1
                                by_member = "unknown"
                                for member in server.members:
                                    if user_lookup(member, str(d[2])):
                                        by_member = member.name
                                d_nid = str(d[0]).ljust(5)
                                d_date = str(datetime.date.fromtimestamp(int(d[3]))).ljust(15)
                                d_by = by_member.ljust(20)
                                msg += d_nid + d_date + d_by + d[4].decode('ascii') + '\n'
                            msg += '```'
                            if note_cnt > 0:
                                await return_channel.send(msg)
                else:
                    await channel.send("Unfortunately member `{}` can't be found in the system, check the spelling or try finding it by id.".format(user))
        else:
            await channel.send("You don't have permissions to lookup other members' expiration date.")
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
      return_channel = server.get_member(message.author.id)
      await return_channel.send(msg)

# Helper function to check your donation expiration
async def donor_expire(message):
    server = client.get_guild(discord_server)
    msg = message.content.lower().split()
    channel = message.channel
    if len(msg) > 2:
        if (roleacc(message, 'super') or roleacc(message, 'admin')):
            user = ' '.join(msg[2:])
            discordid = None
            discordname = ""
            # lookup the userid, a bit clunky but fastest way.
            count = 0
            duplicatemembers = []
            for member in server.members:
                if user_lookup(member, user):
                   discordid = str(member.id)
                   discordname = member.name
                   count = count + 1
                   duplicatemembers.append(member)
            if count > 1:
                dup_msg = "I have discovered multiple users with this name.\nVerify and try it with the discriminator or id.\n"
                dup_msg += "\n".rjust(35, '-')
                for i, member in enumerate(duplicatemembers):
                    dup_msg += str(i + 1) + ". **" + member.name + "#" + member.discriminator + "** (" + str(member.id) + ")\n"
                await channel.send(dup_msg)
            else:
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
                        await channel.send("The subscription for `{}` will expire on `{}`.".format(discordname, str(datetime.date.fromtimestamp(validity))))
                        return_channel = message.channel
                        if return_channel.name in channels_admin or str(message.channel.type) != 'text':
                            db = db_connect()
                            c = db.cursor()
                            c.execute("SELECT * FROM notes WHERE discord_id = '{}' ORDER BY nid ASC;".format(discordid))
                            data = c.fetchall()
                            c.close()
                            db_close(db)

                            note_cnt = 0
                            msg = '```'
                            msg += 'Notes for {}\n'.format(discordname)
                            msg += '\n'.rjust(50, '-')
                            msg += 'nid'.ljust(5) + 'date'.ljust(15) + 'by'.ljust(20) +'note\n'
                            msg += '\n'.rjust(50, '-')
                            for i, d in enumerate(data):
                                note_cnt = note_cnt + 1
                                by_member = "unknown"
                                for member in server.members:
                                    if user_lookup(member, str(d[2])):
                                        by_member = member.name
                                d_nid = str(d[0]).ljust(5)
                                d_date = str(datetime.date.fromtimestamp(int(d[3]))).ljust(15)
                                d_by = by_member.ljust(20)
                                msg += d_nid + d_date + d_by + d[4].decode('ascii') + '\n'
                            msg += '```'
                            if note_cnt > 0:
                                await message_channel.send(msg)
                    else:
                        await channel.send("Unfortunately member `{}` can't be found in the system, check the spelling or try finding it by id.".format(user))
        else:
            await channel.send("You don't have permissions to lookup other members' expiration date.")
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
          return_channel = server.get_member(message.author.id)
          await return_channel.send("Your subscription will expire on `{}`.".format(str(datetime.date.fromtimestamp(validity))))
      else:
          await channel.send("Unfortunately you are not known in the system, please contact a moderator if you have donated.")

# Function to change a donor account to a new account
async def donor_change(message):
    server = client.get_guild(discord_server)
    channel = message.channel
    msg = message.content.lower().split()
    if len(msg) < 4:
        await channel.send("You are missing a parameter to the command, please verify and retry.")
    else:
        # instance of server for later use
        server = client.get_guild(discord_server)
        # We expect these values.
        user = msg[2]
        newuser = msg[3]
        if user == newuser:
            await channel.send("Both ID's must be different from eachother.")
            return
        # Member objects for later use
        omember = None
        nmember = None

        # discordid
        odiscordid = None
        ndiscordid = None
        # lookup the userid, a bit clunky but fastest way.
        for member in server.members:
            if user_lookup(member, user):
               odiscordid = str(member.id)
               omember = member
            if user_lookup(member, newuser):
               ndiscordid = str(member.id)
               nmember = member
            if odiscordid is not None and ndiscordid is not None:
               break

        if odiscordid is not None and ndiscordid is not None:
            # verify existence of rol on the server
            db = db_connect()
            c = db.cursor()
            c.execute("SELECT init, discord_id FROM donor WHERE discord_id = '{}';".format(odiscordid))
            row = c.fetchone()
            c.close()
            db_close(db)

            # If the donor exists, add a payment & update the validity
            if row is not None:
                now = int(time.time())
                init = row[0] if row[0] != 0 else odiscordid
                oldmember = row[1]

                db = db_connect()
                c = db.cursor()
                historyadded = False
                try:
                    c.execute("""INSERT INTO history (init, discord_id, updated) VALUES (%s, %s, %s)""", (init, oldmember, now))
                    db.commit()
                    historyadded = True
                except MySQLdb.Error as e:
                    db.rollback()
                    watchdog(str(e))
                c.close()
                db_close(db)

                if historyadded:
                    db = db_connect()
                    c = db.cursor()
                    try:
                        c.execute ("""UPDATE donor SET discord_id=%s, init=%s WHERE discord_id=%s""", (ndiscordid, init, oldmember))
                        db.commit()
                    except:
                        db.rollback()
                    c.close()
                    db_close(db)
                    try:
                        # Add roles to new user
                        role = discord.utils.get(server.roles, name=donor_role)
                        await client.add_roles(nmember, role)
                        watchdog('Debug: Member {} updated to {}'.format(omember.name, nmember.name))
                    except:
                        watchdog('Error occured: Member {} not updated to {}'.format(omember.name, nmember.name))
                        await channel.send("There was an error trying to update member subscription from `{}` to `{}`.".format(omember.name, nmember.name))
                    await channel.send("Updated member subscription from `{}` to `{}`.".format(omember.name, nmember.name))
                else:
                    await channel.send("There was a problem adding a donation for donor `{}`. Contact an admin if this problem persists".format(discordname))
            # If the donor doesn't exist, create a new entry for the donors, calculate the validity & add a payment
            else:
                await channel.send("This user you're trying to change isn't a donor yet, try adding the user through the `add` command".format(user))
        else:
            await channel.send("One of the users couldn't be found, try again with different parameters".format(user))


# Function to add monitored channels to the database
async def donor_add(message):
    server = client.get_guild(discord_server)
    channel = message.channel
    msg = message.content.lower().split()
    if len(msg) < 4:
        await channel.send("You are missing a parameter to the command, please verify and retry.")
    else:
        # instance of server for later use
        # We expect these values.
        # user = msg[2]
        user = ""
        for x in range(2, len(msg)-1):
            user = user + " " + msg[x].strip()
        user = user.strip()
        month = msg[len(msg)-1]

        discordid = None
        discordname = ""
        discordmember = None
        # lookup the userid, a bit clunky but fastest way.
        count = 0
        duplicatemembers = []
        for member in server.members:
            if user_lookup(member, user):
               discordid = str(member.id)
               discordname = member.name
               discordmember = member
               count = count + 1
               duplicatemembers.append(member)
        if count > 1:
            dup_msg = "I have discovered multiple users with this name.\nVerify and try it with the discriminator or id.\n"
            dup_msg += "\n".rjust(35, '-')
            for i, member in enumerate(duplicatemembers):
                dup_msg += str(i + 1) + ". **" + member.name + "#" + member.discriminator + "** (" + member.id + ")\n"
            await channel.send(dup_msg)
        else:
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
                        watchdog(str(e))
                    c.close()
                    db_close(db)

                    if donationadded:
                        db = db_connect()
                        c = db.cursor()
                        try:
                            c.execute ("""UPDATE donor SET validdate=%s WHERE discord_id=%s""", (valid, discordid))
                            db.commit()
                        except:
                            db.rollback()
                        c.close()
                        db_close(db)
                        if old_valid < created:
                            try:
                                role = discord.utils.get(server.roles, name=donor_role)
                                await discordmember.add_roles(role, reason="Donation made for {} months".format(month))
                            except Exception:
                                watchdog(traceback.format_exc())
                                watchdog(sys.exc_info()[0])
                                if bot_debug == 1:
                                    watchdog('Debug: Member {} should be added now'.format(discordname))
                                await channel.send("There was an error trying to add `{}` to the `{}`.".format(discordname, donor_role))
                        await channel.send("Added a contribution for `{} months` for user `{}` it will expire at `{}`".format(month, discordname, str(datetime.date.fromtimestamp(valid))))
                    else:
                        await channel.send("There was a problem adding a donation for donor `{}`. Contact an admin if this problem persists".format(discordname))
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
                        watchdog(str(e))
                    c.close()
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
                            watchdog(str(e))
                        c.close()
                        db_close(db)

                        if donationadded:
                            role = discord.utils.get(server.roles, name=donor_role)
                            watchdog(str(role.name) + ' - ' + str(role.id))
                            try:
                                await discordmember.add_roles(role, reason="Donation made for {} months".format(month))
                            except Exception:
                                watchdog(traceback.format_exc())
                                watchdog(sys.exc_info()[0])
                                if bot_debug == 1:
                                    watchdog('Member {} could not be added'.format(discordname))
                                await channel.send("Forbidden error: There was an error trying to add `{}` to the `{}`.".format(discordname, donor_role))
                            await channel.send("Added donor `{}` to the database with a first contribution for `{} months`".format(discordname, month))
                            if donor_enablewelcome == 1:
                                welcome = None
                                for member in server.members:
                                    if member.id == discordid:
                                        usr = member
                                for channel in server.channels:
                                    if channel.name == donor_botroom:
                                        chan = channel
                                    if channel.name == donor_welcomeroom:
                                        welcome = channel
                                for role in server.roles:
                                    if role.name == donor_chatmods:
                                        mod = role
                                if welcome != None:
                                    await welcome.send(donor_newmsg.format(usr, chan, mod))
                        else:
                            await channel.send("There was a problem adding a donation for donor `{}`. Contact an admin if this problem persists".format(user))
                    else:
                        await channel.send("An error occurred adding donor `{}` to the database, try again later or contact and administrator".format(user))
            else:
                await channel.send("An error occurred trying to add donor `{}` to the database".format(user))


# Function to remove months from a user.
async def donor_remove(message):
    server = client.get_guild(discord_server)
    channel = message.channel
    msg = message.content.lower().split()
    if len(msg) < 4:
        await channel.send("You are missing a parameter to the command, please verify and retry.")
    else:
        # instance of server for later use
        # We expect these values.
        user = ""
        for x in range(2, len(msg)-1):
            user = user + " " + msg[x].strip()
        user = user.strip()
        month = msg[len(msg)-1]

        discordid = None
        discordname = ""
        discordmember = None
        # lookup the userid, a bit clunky but fastest way.
        count = 0
        duplicatemembers = []
        for member in server.members:
            if user_lookup(member, user):
               discordid = str(member.id)
               discordname = member.name
               discordmember = member
               count = count + 1
               duplicatemembers.append(member)
        if count > 1:
            dup_msg = "I have discovered multiple users with this name.\nVerify and try it with the discriminator or id.\n"
            dup_msg += "\n".rjust(35, '-')
            for i, member in enumerate(duplicatemembers):
                dup_msg += str(i + 1) + ". **" + member.name + "#" + member.discriminator + "** (" + member.id + ")\n"
            await channel.send(dup_msg)
        else:
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
                    valid = new_valid_remove_time(old_valid, month)
                    watchdog(str(valid))
                    db = db_connect()
                    c = db.cursor()
                    donationadded = False
                    try:
                        c.execute("""INSERT INTO donation (discord_id, amt, donationdate) VALUES (%s, %s, %s)""", (discordid, '-' + month, created))
                        db.commit()
                        donationadded = True
                    except MySQLdb.Error as e:
                        db.rollback()
                        watchdog(str(e))
                    c.close()
                    db_close(db)

                    if donationadded:
                        db = db_connect()
                        c = db.cursor()
                        try:
                            c.execute ("""UPDATE donor SET validdate=%s WHERE discord_id=%s""", (valid, discordid))
                            db.commit()
                        except:
                            db.rollback()
                        c.close()
                        db_close(db)
                        await channel.send("Removed `{} months` from user `{}` it will expire at `{}`".format(month, discordname, str(datetime.date.fromtimestamp(valid))))
                    else:
                        await channel.send("There was a problem removing a donation for donor `{}`. Contact an admin if this problem persists".format(discordname))
                else:
                    await channel.send("An error occurred trying to remove months from donor `{}` to the database, try again later or contact an administrator".format(user))
            else:
                await channel.send("An error occurred trying to remove months from donor `{}`".format(user))
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

# Helper function to determine the validity
def new_valid_remove_time(valid, m):
    # convert month to int, we jump one month ahead to get the last month
    m = int(m)
    # Convert to datetime objects for relative adding
    d_valid = datetime.date.fromtimestamp(valid)
    # Add months
    d_new_valid = d_valid - relativedelta(months=m)

    watchdog(str(d_valid) + ' - ' + str(d_new_valid))
    ldom = last_day_of_month(datetime.datetime.strptime(str(d_new_valid), '%Y-%m-%d'))
    # get unixtimestamp
    t_new_valid = int(time.mktime(ldom.timetuple()))
    return t_new_valid

def last_day_of_month(any_day):
    next_month = any_day.replace(day=28) + datetime.timedelta(days=4)  # this will never fail
    return next_month - datetime.timedelta(days=next_month.day)

# Helper function to check permissions
def roleacc(message, group):
    # distinguish whether the user is high privileged than @everyone
    stopUnauth = False
    # in PM determine the user roles from the server settings.
    if message.author.__class__.__name__ ==  'User':
        msrv = client.get_guild(discord_server)
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
            if str(usr.id) == sid:
                stopUnauth = True
                break
        return stopUnauth
    elif group == 'admin':
        try:
            getattr(usr, 'roles')
        except AttributeError:
            watchdog("-- Debug info -- ")
            watchdog("type: " + message.type.name)
            watchdog("channel: " + message.channel.name)
            watchdog("bot: " + str(message.author.bot))
            return stopUnauth

        for role in usr.roles:
           if str(role.id) in roles_admin:
             stopUnauth = True
             break
        return stopUnauth
    return stopUnauth

# Helper function to get the correct member
def user_lookup(member, user):
    regex = _regex_from_encoded_pattern('/<@(\d+)>/si')
    match_id = regex.findall(user)
    if len(match_id) == 1:
        user = match_id[0]
    regex = _regex_from_encoded_pattern('/@(.+)/si')
    match_id = regex.findall(user)
    if len(match_id) == 1:
        user = match_id[0]
    return str(member.name).lower() == user.lower() or str(member.name + '#' + member.discriminator).lower() == user or str(member.id) == user or str(member.nick).lower() == user.lower()

# Helper for regex
def _regex_from_encoded_pattern(s):
    if s.startswith('/') and s.rfind('/') != 0:
        # Parse it: /PATTERN/FLAGS
        idx = s.rfind('/')
        pattern, flags_str = s[1:idx], s[idx+1:]
        flag_from_char = {
            "i": re.IGNORECASE,
            "l": re.LOCALE,
            "s": re.DOTALL,
            "m": re.MULTILINE,
            "u": re.UNICODE,
        }
        flags = 0
        for char in flags_str:
            try:
                flags |= flag_from_char[char]
            except KeyError:
                raise ValueError("unsupported regex flag: '%s' in '%s' "
                                 "(must be one of '%s')"
                                 % (char, s, ''.join(flag_from_char.keys())))
        return re.compile(s[1:idx], flags)
    else: # not an encoded regex
        return re.compile(re.escape(s))

# --- db functions ---
# Helper function for levenshtein calculations.
def levenshtein(s1, s2):
    if len(s1) < len(s2):
        return levenshtein(s2, s1)

    # len(s1) >= len(s2)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1 # j+1 instead of j since previous_row and current_row are one character longer
            deletions = current_row[j] + 1       # than s2
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

# Helper function to do logging
def watchdog(message):
    print(message)
    if bot_debug == 1:
        date = str(datetime.datetime.now().strftime("%Y-%m-%d - %I:%M:%S"))
        f = open(os.path.join('log', str(datetime.datetime.now().strftime("%Y-%m-%d") + '-debug.log')), 'a')
        f.write(date + " # " + message + '\n')
        f.close()

# Helper function to get all mods and higher their id
def get_management():
    mod_ids = []
    server = client.get_guild(discord_server)
    for member in server.members:
        for role in member.roles:
            if role.id in roles_admin:
                mod_ids.append(member.id)
    return mod_ids

def variable_get(variable):
    # Initialize db
    db = db_connect()
    c = db.cursor()

    c.execute("SELECT value FROM system WHERE variable = '{}';".format(variable))
    # Fetch a single row using fetchone() method.
    d = c.fetchone()
    if d is not None:
        returnval = d[0]
    else:
        returnval = ""
    c.close()
    db_close(db)
    return returnval

def variable_set(variable, value):
    # Initialize db
    db = db_connect()
    c = db.cursor()

    c.execute("SELECT value FROM system WHERE variable = '{}';".format(variable))
    # Fetch a single row using fetchone() method.
    d = c.fetchone()
    c.close()
    db_close(db)
    success = False
    if d is None:
        try:
            db = db_connect()
            c = db.cursor()
            c.execute("""INSERT INTO system (variable, value) VALUES (%s, %s)""", (variable, value))
            db.commit()
            c.close()
            db_close(db)
            success = True
        except:
            watchdog('something went wrong inserting the variable')
            success = False
    else:
        try:
            db = db_connect()
            c = db.cursor()
            query = "UPDATE system SET value = %s WHERE variable = %s"
            c.execute(query, (value, variable))
            db.commit()
            c.close()
            db_close(db)
            success = True
            watchdog('Update variable {}'.format(variable))
        except MySQLdb.Error as err:
            watchdog(str(err))
            success = False
        except:
            watchdog('something went wrong updating the variable')
            success = False
    return success

# Helper function to execute a query and return the results in a list object
def db_connect():
    # Setup the db connection with the global params
    connection = MySQLdb.connect(host=sql_host, port=sql_port, user=sql_user, passwd=sql_pass, db=sql_db)
    return connection

def db_close(connection):
    connection.close()
# --- End db functions ---
# --- End helper Methods ---

client.run(discord_bothash)
