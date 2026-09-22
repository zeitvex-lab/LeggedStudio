<template>
  <div>
    <pre class="text-xs"><code class="language-html" v-html="htmlData"></code></pre>
  </div>
</template>

<script lang="ts" setup>
import { defineProps, computed } from 'vue';
import hljs from 'highlight.js/lib/common';
// import 'highlight.js/styles/default.min.css';
import 'highlight.js/styles/atom-one-dark.min.css';
import protobuf from 'highlight.js/lib/languages/protobuf';

hljs.registerLanguage('protobuf', protobuf);

const props = defineProps(['text', 'lang']);

const htmlData = computed(() => {
  const text = props.text?.replace(/^```/, '').replace(/```$/, '') || '';

  try {
    const highlighted = hljs.highlight(text, {
      language: props.lang || 'plaintext'
    });
    return highlighted.value;
  } catch (error) {
    console.log('不支持的语言:', props.lang);
    return hljs.highlight(text, { language: 'plaintext' }).value;
  }
});
</script>
