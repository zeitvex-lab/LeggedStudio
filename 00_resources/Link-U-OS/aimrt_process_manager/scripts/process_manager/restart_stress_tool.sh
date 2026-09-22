#!/bin/bash


get_errors() {

curl -i http://127.0.0.1:50080/json/stop_all_apps  >/dev/null 2>&1

#echo ""

ps -auxf |grep "process_manager --cfg_file_path" |grep -v grep |awk '{print $2}'| xargs -r sudo kill -15

sleep 20

cat /agibot/log/process_manager/process_manager.log |grep Error  |grep "Recv Intermediate process Channel code"

}

cnt=1
while true; do
  result=$(get_errors)
  if [[ -n $result ]]; then
    printf '%s\n' "$result"
    exit 0
  fi
  sleep 3
  echo "continue...[$cnt]"
  ((cnt++))

done
