<template>
  <div class="h-full flex items-center">
    <div class="whitespace-nowrap flex items-center">
      <SvgIcon name="robot" class="inline-block w-10 h-10 mr-4"></SvgIcon>
      <span class="text-xl inline-blick mt-2 text-white">AimRT Viz</span>
    </div>
    <div class="flex-1 flex justify-center">
      <Connector></Connector>
    </div>
    <div>
      <TimerButton @refresh="periodGetData"></TimerButton>
    </div>
  </div>
</template>
<script setup lang="ts">
import TimerButton from './TimerButton.vue';
import Connector from './Connector.vue';
import { updateTimerTickTimes } from '@/contexts/ConnectorContext';
import SvgIcon from '@/components/SvgIcon.vue';

function periodGetData() {
  updateTimerTickTimes();
}
</script>
