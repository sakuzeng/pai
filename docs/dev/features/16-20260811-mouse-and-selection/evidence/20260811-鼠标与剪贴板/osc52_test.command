#!/bin/zsh
printf '\033]52;c;%s\007' "$(printf 'OSC52-BEL-OK' | base64)"
sleep 1
printf '\033]52;c;%s\033\\' "$(printf 'OSC52-ST-OK' | base64)"
sleep 1
echo done > /tmp/osc52-done
sleep 1
exit
