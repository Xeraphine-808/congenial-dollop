#!/bin/bash

# Asignamos 10GB de RAM (dejando 6GB para el sistema)
/usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java -Xmx10G -Xms4G -XX:+UseG1GC -XX:+UnlockExperimentalVMOptions -XX:MaxGCPauseMillis=100 -XX:+DisableExplicitGC -XX:TargetSurvivorRatio=90 -XX:G1NewSizePercent=35 -XX:G1MaxNewSizePercent=60 -XX:G1MixedGCLiveThresholdPercent=90 -XX:+AlwaysPreTouch -jar forge-1.12.2-14.23.5.2860.jar nogui