#!/usr/bin/env bash
# Deploys the hunter to AWS Lambda on a schedule. The schedule stays off until you run with ENABLE=1.
# Usage: ALERT_EMAIL=you@example.com [ENABLE=1] [PACKAGE_DIR=path] bash deployment/aws/deploy.sh
set -euo pipefail

ACCOUNT=651709558319 # OM's Personal
export AWS_PROFILE=default AWS_REGION=ap-south-1 AWS_DEFAULT_REGION=ap-south-1
export MSYS_NO_PATHCONV=1 # stops Git Bash rewriting /oracle-hunter/... into a Windows path
NAME=oracle-hunter
PARAM=/oracle-hunter/oci-private-key
REPO=$(cd "$(dirname "$0")/../.." && pwd)
OCI_CONFIG="$HOME/.oci/config"
: "${ALERT_EMAIL:?Set ALERT_EMAIL}"

[ "$(aws sts get-caller-identity --query Account --output text)" = "$ACCOUNT" ] || { echo "Wrong AWS account"; exit 1; }

oci_value() { grep -E "^$1=" "$OCI_CONFIG" | head -1 | cut -d= -f2- | tr -d '\r'; }
KEY_FILE=$(oci_value key_file); KEY_FILE=${KEY_FILE/#\~/$HOME}
SSH_KEY=$(grep -E '^ssh_public_key:' "$REPO/config.yaml" | sed -E 's/^ssh_public_key: *"?([^"]*)"?.*/\1/' | tr -d '\r')
[ -n "$SSH_KEY" ] || { echo "No ssh_public_key in config.yaml"; exit 1; }

# --- Package
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
if [ -z "${PACKAGE_DIR:-}" ]; then
  PACKAGE_DIR="$WORK/p"
  py -3 -m pip install -q --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
    --only-binary=:all: --target "$(cygpath -w "$PACKAGE_DIR")" oci pydantic pyyaml rich filelock
  py -3 "$(cygpath -w "$REPO/deployment/aws/prune_oci.py")" "$(cygpath -w "$PACKAGE_DIR")"
fi
cp -r "$REPO/src/free_tier_hunter" "$PACKAGE_DIR/"
cp "$REPO/deployment/aws/lambda_handler.py" "$PACKAGE_DIR/"
find "$PACKAGE_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +
py -3 -c "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" "$(cygpath -w "$WORK/hunter")" "$(cygpath -w "$PACKAGE_DIR")"

# --- Private key, encrypted. The CLI reads the file, so the key never appears in a command line.
aws ssm put-parameter --name "$PARAM" --type SecureString --overwrite --value "file://$(cygpath -m "$KEY_FILE")" >/dev/null

# --- Alerts
TOPIC=$(aws sns create-topic --name "$NAME" --query TopicArn --output text)
if ! aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" --query 'Subscriptions[].Endpoint' --output text | grep -qF "$ALERT_EMAIL"; then
  aws sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
fi

# --- Schedule rule, created first so the role can be scoped to it. Off unless ENABLE=1.
STATE=DISABLED; [ "${ENABLE:-0}" = 1 ] && STATE=ENABLED
RULE=$(aws events put-rule --name "$NAME" --schedule-expression 'rate(3 minutes)' --state "$STATE" --query RuleArn --output text)

# --- Role: only what the hunter needs
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
if ! ROLE=$(aws iam get-role --role-name "$NAME-lambda" --query Role.Arn --output text 2>/dev/null); then
  ROLE=$(aws iam create-role --role-name "$NAME-lambda" --assume-role-policy-document "$TRUST" --query Role.Arn --output text)
  NEW_ROLE=1
fi
aws iam put-role-policy --role-name "$NAME-lambda" --policy-name hunter --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[
{\"Effect\":\"Allow\",\"Action\":[\"logs:CreateLogStream\",\"logs:PutLogEvents\"],\"Resource\":\"arn:aws:logs:$AWS_REGION:$ACCOUNT:log-group:/aws/lambda/$NAME:*\"},
{\"Effect\":\"Allow\",\"Action\":\"ssm:GetParameter\",\"Resource\":\"arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter$PARAM\"},
{\"Effect\":\"Allow\",\"Action\":\"events:DisableRule\",\"Resource\":\"$RULE\"},
{\"Effect\":\"Allow\",\"Action\":\"sns:Publish\",\"Resource\":\"$TOPIC\"}]}"
[ -n "${NEW_ROLE:-}" ] && sleep 15 # a new role takes a moment to become usable

# --- Logs kept for 7 days, so they can't build up forever
aws logs create-log-group --log-group-name "/aws/lambda/$NAME" 2>/dev/null || true
aws logs put-retention-policy --log-group-name "/aws/lambda/$NAME" --retention-in-days 7

# --- Function
ENV_FILE="$WORK/env.json"
py -3 -c "import json,sys; v=sys.argv[2:]; open(sys.argv[1],'w').write(json.dumps({'Variables':dict(zip(['OCI_USER','OCI_FINGERPRINT','OCI_TENANCY','OCI_REGION','SSH_PUBLIC_KEY','OCI_KEY_PARAMETER','RULE_NAME','TOPIC_ARN'],v))}))" \
  "$(cygpath -w "$ENV_FILE")" "$(oci_value user)" "$(oci_value fingerprint)" "$(oci_value tenancy)" "$(oci_value region)" "$SSH_KEY" "$PARAM" "$NAME" "$TOPIC"
ZIP="fileb://$(cygpath -m "$WORK/hunter.zip")"
ENV_ARG="file://$(cygpath -m "$ENV_FILE")"
if aws lambda get-function --function-name "$NAME" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$NAME" --zip-file "$ZIP" >/dev/null
  aws lambda wait function-updated --function-name "$NAME"
  aws lambda update-function-configuration --function-name "$NAME" --environment "$ENV_ARG" >/dev/null
else
  # The hunter can wait up to 5 minutes for a new instance to reach RUNNING.
  aws lambda create-function --function-name "$NAME" --runtime python3.12 --architectures x86_64 \
    --handler lambda_handler.handler --role "$ROLE" --timeout 360 --memory-size 512 \
    --environment "$ENV_ARG" --zip-file "$ZIP" >/dev/null
fi
aws lambda wait function-updated --function-name "$NAME" 2>/dev/null || aws lambda wait function-active-v2 --function-name "$NAME"
# No retries: the next scheduled run is the retry.
aws lambda put-function-event-invoke-config --function-name "$NAME" --maximum-retry-attempts 0 >/dev/null

# --- Connect the schedule
aws lambda add-permission --function-name "$NAME" --statement-id "$NAME-schedule" --action lambda:InvokeFunction \
  --principal events.amazonaws.com --source-arn "$RULE" >/dev/null 2>&1 || true
FN=$(aws lambda get-function --function-name "$NAME" --query Configuration.FunctionArn --output text)
aws events put-targets --rule "$NAME" --targets "Id=1,Arn=$FN" >/dev/null

# --- Email if it keeps failing, e.g. the Oracle key stops working
aws cloudwatch put-metric-alarm --alarm-name "$NAME-failing" --namespace AWS/Lambda --metric-name Errors \
  --dimensions "Name=FunctionName,Value=$NAME" --statistic Sum --period 3600 --evaluation-periods 1 \
  --threshold 10 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching \
  --alarm-actions "$TOPIC"

echo "Deployed $NAME in account $ACCOUNT, region $AWS_REGION. Schedule: $STATE"
