<template>
  <div class="status-icon" :class="status ? 'success' : 'error'">
    <svg v-if="status" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M5 12L10 17L19 8"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <svg v-else viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M6 18L18 6M6 6L18 18"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </div>
</template>

<script setup lang="ts">
interface Props {
  status: boolean;
  size?: string | number;
}

const props = withDefaults(defineProps<Props>(), {
  size: '24px'
});
</script>

<style scoped>
.status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: v-bind('props.size');
  height: v-bind('props.size');
  border-radius: 4px;
}

.status-icon svg {
  width: 70%;
  height: 70%;
}

.success {
  background-color: #e6f7ee;
  color: #10b981;
}

.error {
  background-color: #fee2e2;
  color: #ef4444;
}
</style>
