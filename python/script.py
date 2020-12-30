import argparse
import logging
import sys
import boto3
import time
from datetime import datetime

# Setup logging
log = logging.getLogger('script')
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Create file handler which logs debug+ messages
fh = logging.FileHandler('script_output-{}.log'.format(datetime.now().strftime('%Y_%m_%d-%H%M%S')))
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
log.addHandler(fh)
# Create console handler with a higher log level
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
log.addHandler(ch)

# Create parser
parser = argparse.ArgumentParser(description='Utility to associate phone numbers to a Chime VC or VCG')

# Add arguments
parser.add_argument('--voice_connector_id',
                    type=str,
                    help='The Voice Connector Id')

parser.add_argument('--voice_connector_group_id',
                    type=str,
                    help='The Voice Connector Group Id')

# Execute the parser
args = parser.parse_args()

# Extract the account id from creds
sts_client = boto3.client('sts')
aws_account_id = sts_client.get_caller_identity()['Account']

# Extract variable values from args
voice_connector_id = args.voice_connector_id
voice_connector_group_id = args.voice_connector_group_id

# Validate VC/VCG arg is passed
if voice_connector_id == None and voice_connector_group_id == None:
  raise ValueError('Invalid arguments: Either VC or VCG ID is required')

if voice_connector_id != None and voice_connector_group_id != None:
  raise ValueError('Invalid arguments: Both VC and VCG ID cannot be provided')

is_voice_connector_association = voice_connector_id != None

# Initialize variables
unassigned_phone_numbers = []
next_token = None
chime_client = boto3.client('chime')

log.info('Executing script to assign unassigned phone numbers of account %s to %s with id %s',
  aws_account_id,
  'voice connector' if is_voice_connector_association else 'voice connector group',
  voice_connector_id if is_voice_connector_association else voice_connector_group_id,
)
should_proceed = raw_input('Proceed? (y/n): ')
if should_proceed != 'y':
  log.info('Exiting')
  sys.exit(0)

# List all unassigned phone numbers
log.info('Listing all unassigned phone numbers in the account %s', aws_account_id)
while True:
  if next_token != None:
    response = chime_client.list_phone_numbers(
      Status='Unassigned',
      NextToken=next_token,
    )
  else:
    response = chime_client.list_phone_numbers(
      Status='Unassigned',
    )

  log.debug('Response from list phone numbers %s', response)

  if 'PhoneNumbers' not in response:
    log.error('No phone numbers object in list response')
    break

  for phone_number in response['PhoneNumbers']:
    unassigned_phone_numbers.append(phone_number['E164PhoneNumber'])

  if 'NextToken' not in response or response['NextToken'] == None:
    break

  next_token = response['NextToken']

  time.sleep(1)

log.info('Found %s unassigned phone numbers', len(unassigned_phone_numbers))

all_successful_phone_numbers = []
all_failed_phone_numbers = []

# Associate unassigned phone numbers to the VC
batch_size = 10
for index in xrange(0, len(unassigned_phone_numbers), batch_size):
  phone_numbers = unassigned_phone_numbers[index:index + batch_size]
  log.info('Associating phone numbers to %s %s: %s', 
    'voice connector' if is_voice_connector_association else 'voice connector group',
    voice_connector_id if is_voice_connector_association else voice_connector_group_id,
    ', '.join(phone_numbers),
  )

  # Make a request to associate phone numbers
  if is_voice_connector_association:
    response = chime_client.associate_phone_numbers_with_voice_connector(
      VoiceConnectorId=voice_connector_id,
      E164PhoneNumbers=phone_numbers,
    )
  else:
    response = chime_client.associate_phone_numbers_with_voice_connector_group(
      VoiceConnectorGroupId=voice_connector_group_id,
      E164PhoneNumbers=phone_numbers,
    )

  log.debug('Response from associating phone numbers %s: %s', 
    ', '.join(phone_numbers),
    response,
  )

  # Extract failed phone numbers
  failed_phone_numbers = []
  if 'PhoneNumberErrors' in response:
    for phone_number_error in response['PhoneNumberErrors']:
      failed_phone_numbers.append(phone_number_error['PhoneNumberId'])

  # Gather successfully associated phone numbers
  successful_phone_numbers = [x for x in phone_numbers if x not in failed_phone_numbers]
  
  log.info('Successfully associated phone numbers to %s %s: %s', 
    'voice connector' if is_voice_connector_association else 'voice connector group',
    voice_connector_id if is_voice_connector_association else voice_connector_group_id,
    ', '.join(phone_numbers),
  )
  
  if len(failed_phone_numbers) > 0:
    log.error('Failed to associate phone numbers %s', ', '.join(failed_phone_numbers))

  all_successful_phone_numbers.extend(successful_phone_numbers)
  all_failed_phone_numbers.extend(failed_phone_numbers)

  time.sleep(1)

# Summarize script result
log.info('Script summary:')
log.info('Total:    %s', len(unassigned_phone_numbers))
log.info('Success:  %s', len(all_successful_phone_numbers))
log.info('Failure:  %s', len(all_failed_phone_numbers))

# Close all the log handlers
for handler in log.handlers:
  handler.close()
  log.removeFilter(handler)
