########################################################
#
# Intended to be run as a playbook from within LC
#
########################################################

import json
import urllib.parse
import urllib.request
import limacharlie

lc_regions = {
  "us": "LCIO-NYC3-USAGE-V1",
  "ca": "LCIO-TOR1-USAGE-V1",
  "in": "LCIO-BLR1-USAGE-V1",
  "uk": "LCIO-LON1-USAGE-V1",
  "eu": "LCIO-AMS3-USAGE-V1",
  "au": "LCIO-SYD1-USAGE-V1",
  "exp": "LCIO-EXP1-USAGE-V1"
}

# create a new org
def create_org(my_mgr, org_name, org_location, iac_template=None):
  new_org = my_mgr.createNewOrg(name=org_name,location=org_location,template=iac_template)
  new_oid = new_org["data"]["oid"]
  print(f"Organization created with ID: {new_oid}")
  return new_oid
  
# create a new group
def create_group(my_mgr, org_name):
  new_group = my_mgr.createGroup(name=org_name)
  new_gid = new_group["data"]["gid"]
  print(f"Group created with ID: {new_gid}")
  return new_gid

# add owner to the new group
def add_owner(my_mgr, new_gid, owner):
  print(f"Adding owner {owner} to group {new_gid}")
  return my_mgr.addGroupOwner(groupId=new_gid,ownerEmail=owner)

# add group to the new org
def add_group_org(my_mgr, new_gid, new_oid):
  print(f"Adding group {new_gid} to org {new_oid}")
  return my_mgr.addGroupOrg(groupId=new_gid,oid=new_oid)

# add users to the new group
def add_group_members(my_mgr, new_gid, users):
  print(f"Adding users {users} to group {new_gid}")
  for each_user in users:
    my_mgr.addGroupMember(groupId=new_gid,memberEmail=each_user)

# set permissions for the new group
def set_group_permissions(my_mgr, new_gid, permissions):
  print(f"Setting permissions for group {new_gid}")
  return my_mgr.setGroupPermissions(groupId=new_gid,permissions=permissions)

# get the group permissions from the secrets manager
def get_group_permissions(my_mgr, secret_name):
  group_permissions = limacharlie.Hive(my_mgr, "secret").get(secret_name).data["secret"]
  return group_permissions.strip().replace('\n','').split(',')

# get the iac template from the url if it starts with https://, otherwise assume it's a payload and get it from the payloads
def get_iac_template(my_mgr, iac_url):
  if iac_url.startswith("https://"):
    iac_template = urllib.request.urlopen(iac_url).read()
    return iac_template
  else:
    my_payloads = limacharlie.Payloads(my_mgr)
    iac_template = my_payloads.get(name=iac_url)
    return iac_template.decode('utf-8')
  

# post statuses to slack
def post_to_slack(token, channel, message):
  url = 'https://slack.com/api/chat.postMessage'
  errors = []

  payload = {
    'token': token,
    'channel': channel,
    'text': message
  }

  data = urllib.parse.urlencode(payload).encode('utf-8')
  req = urllib.request.Request(url, data=data, method='POST')
  try:
    with urllib.request.urlopen(req) as response:
      result = json.loads(response.read().decode('utf-8'))
  except Exception as e:
    print(f"An error occurred while posting to Slack channel {channel}: {e}")
    exit(1)
  return result


########################
# this will be playbook stuff
########################

def playbook(sdk, data):
 
  # extract the data from the data object
  data = data["data"]
  lc_user_secret = data["lc_user_secret"]
  users = data["users"]
  owner = data["requestor"]
  slack_secret = data["slack_secret"]
  slack_channel = data["slack_channel"]
  group_perm_secret = data["group_perm_secret"]
  iac_url = data["iac_url"] or None
  org_name = data["org_name"]

  #get org location from the data
  try:
    org_location_slack = data["org_location"]
    org_location = lc_regions[org_location_slack]
  except:
    post_to_slack(slack_token, slack_channel, f":x: Invalid org location: {data['org_location']}")
  
  # get the user secret and slack token from the hive
  user_secret = limacharlie.Hive(sdk, "secret").get(lc_user_secret).data["secret"]
  slack_token = limacharlie.Hive(sdk, "secret").get(slack_secret).data["secret"]
  uid, user_key = user_secret.split("/")

  # instantiate our manager api object - required for org creation stuff
  my_mgr = limacharlie.Manager(secret_api_key=user_key,uid=uid)
  post_to_slack(slack_token, slack_channel, f":rocket: Creating org {org_name} in {org_location}")

  # use an iac template if provided, otherwise create a new org with no template
  if iac_url:
    iac_template = get_iac_template(sdk, iac_url)
  else:
    iac_template = None
  
  # create the org and post to slack
  try:
    new_oid = create_org(my_mgr, org_name, org_location, iac_template)
    post_to_slack(slack_token, slack_channel, f":white_check_mark: Organization created with ID: {new_oid}")
  except Exception as e:
    post_to_slack(slack_token, slack_channel, f":x: Error creating org {org_name} in {org_location}: {e}")
    exit(1)
  
  # create the group and post to slack
  try:
    new_gid = create_group(my_mgr, org_name)
    post_to_slack(slack_token, slack_channel, f":white_check_mark: Group created with ID: {new_gid}")
  except Exception as e:
    post_to_slack(slack_token, slack_channel, f":x: Error creating group {org_name}: {e}")
    exit(1)
  
  # add the owner to the group and post to slack
  try:
    add_owner(my_mgr, new_gid, owner)
    post_to_slack(slack_token, slack_channel, f":white_check_mark: Owner {owner} added to group {new_gid}")
  except Exception as e:
    post_to_slack(slack_token, slack_channel, f":x: Error adding owner {owner} to group {new_gid}: {e}")
    exit(1)

  # add the group to the org and post to slack 
  try:
    add_group_org(my_mgr, new_gid, new_oid)
    post_to_slack(slack_token, slack_channel, f":white_check_mark: Group {new_gid} added to org {new_oid}")
  except Exception as e:
    post_to_slack(slack_token, slack_channel, f":x: Error adding group {new_gid} to org {new_oid}: {e}")
    exit(1)
  
  # set the permissions for the group and post to slack
  try:
    permissions = get_group_permissions(sdk, group_perm_secret)
    set_group_permissions(my_mgr, new_gid, permissions)
    post_to_slack(slack_token, slack_channel, f":white_check_mark: Permissions set for group {new_gid}")
  except Exception as e:
    post_to_slack(slack_token, slack_channel, f":x: Error setting permissions for group {new_gid}: {e}")
    exit(1)
  
  # post to slack that we're done
  post_to_slack(slack_token, slack_channel, f":partying_face: Completed creating org {org_name} in {org_location}")
  
  # return the data
  return {
    "data": {
      "oid": new_oid,
      "gid": new_gid,
      "owner": owner,
      "users": users,
      "org_name": org_name,
      "org_location": org_location,
      "slack_channel": slack_channel,
      "iac_url": iac_url
    }
  }
