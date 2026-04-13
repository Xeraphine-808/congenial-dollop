#!/bin/bash

# Asegúrate de cambiar el nombre del archivo .jar por el tuyo exacto.
JAR_NAME="forge-1.12.2-14.23.5.2860.jar"

java -Xms4G -Xmx4G -XX:+UseG1GC -XX:+UnlockExperimentalVMOptions -XX:MaxGCPauseMillis=50 -XX:+DisableExplicitGC -XX:TargetSurvivorRatio=90 -XX:G1NewSizePercent=50 -XX:G1MaxNewSizePercent=80 -XX:G1MixedGCLiveThresholdPercent=35 -XX:+AlwaysPreTouch -XX:+ParallelRefProcEnabled -jar $JAR_NAME nogui