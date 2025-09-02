########################################################
#
# Intended to be run as a playbook from within LC
#
########################################################

import json
import urllib.parse
import urllib.request
import limacharlie

def get_user_ids_by_emails(token, user_emails):
  url = 'https://slack.com/api/users.lookupByEmail'
  user_id_map = {}
  errors = []

  for email in user_emails:
    email = urllib.parse.unquote(email)
    payload = {
      'token': token,
      'email': email
    }

    data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    try:
      with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode('utf-8'))
        if result.get('ok'):
          user_id_map[email] = result['user']['id']
        else:
          errors.append(f"Could not find user for email '{email}': {result.get('error')}")
    except Exception as e:
      errors.append(f"An error occurred while looking up '{email}': {e}")
            
  return {'ok': not errors, 'user_ids': user_id_map, 'errors': errors}

def get_user_email_by_id(token, user_id):
  url = 'https://slack.com/api/users.info'
  payload = {
    'token': token,
    'user': user_id
  }
  data = urllib.parse.urlencode(payload).encode('utf-8')
  req = urllib.request.Request(url, data=data, method='POST')
  with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode('utf-8'))
    return result['user']['profile']['email']

def create_slack_channel(token, channel_name, is_private, user_emails):
  # Look up User IDs from the provided email addresses
  if isinstance(user_emails, str):
    user_emails = user_emails.split(",")
  user_ids = []
  
  if user_emails:
    lookup_result = get_user_ids_by_emails(token, user_emails)
    if not lookup_result.get('ok'):
      return {'ok': False, 'error': f"Failed to look up user IDs: {lookup_result.get('errors')}"}
    user_ids = list(lookup_result.get('user_ids').values())

  # Create the channel
  url = 'https://slack.com/api/conversations.create'
  payload = {
    'token': token,
    'name': channel_name,
    'is_private': is_private
  }
  data = urllib.parse.urlencode(payload).encode('utf-8')
  req = urllib.request.Request(url, data=data, method='POST')
  try:
    with urllib.request.urlopen(req) as response:
      result = json.loads(response.read().decode('utf-8'))
      if result.get('ok'):
        # Invite users if User IDs were found
        if user_ids:
          invite_url = 'https://slack.com/api/conversations.invite'
          invite_payload = {
            'token': token,
            'channel': result['channel']['id'],
            'users': ','.join(user_ids)
          }
          invite_data = urllib.parse.urlencode(invite_payload).encode('utf-8')
          invite_req = urllib.request.Request(invite_url, data=invite_data, method='POST')
          with urllib.request.urlopen(invite_req) as invite_response:
            invite_result = json.loads(invite_response.read().decode('utf-8'))
            return invite_result
        return result
    return result

  except urllib.error.HTTPError as e:
    return {'ok': False, 'error': f'HTTP Error: {e.code} - {e.reason}'}
  except Exception as e:
    return {'ok': False, 'error': f'An error occurred: {e}'}

def playbook(sdk, data):

  slack_data = data["data"]
  
  # Get the secrets we need from LimaCharlie.
  slack_secret = limacharlie.Hive(sdk, "secret").get(slack_data["slack_secret"]).data["secret"]
  slack_token = slack_secret
  
  #parse the data from LC
  channel_name = slack_data["channel_name"]
  users_by_email = slack_data["users"]
  is_private = slack_data["is_private"].lower() == "true" or False

  response = create_slack_channel(slack_token, channel_name, is_private, user_emails=users_by_email)
  response["slack_data"] = slack_data
  response["slack_data"]["src_user_name"] = get_user_email_by_id(slack_token, slack_data["src_user_id"])
  
  headers = {'Content-Type': 'application/json'}
  if response['ok']:
    response["slack_event"] = "slack_channel_created"
    payload = {
      "replace_original": "true",
      "text": ':white_check_mark:\tChannel created successfully. \n\t\t  Channel Name: ' + response['slack_data']['channel_name'] + '\n\t\t Requested by: ' + response['slack_data']['src_user_name']
    }
  else:
    response["slack_event"] = "slack_channel_creation_failed"
    payload = {
      "replace_original": "true",
      "text": ':x:\tChannel creation failed. \n\t\t  Error: ' + response['error'] + '\n\t\t  Requested by: ' + response['slack_data']['src_user_name']
    }
  data = json.dumps(payload).encode('utf-8')
  req = urllib.request.Request(slack_data["response_url"], data=data, method='POST', headers=headers)
  with urllib.request.urlopen(req) as reply_response:
    response["slack_response"] = reply_response.read().decode('utf-8')
  
  return {
    "data": response
    }
