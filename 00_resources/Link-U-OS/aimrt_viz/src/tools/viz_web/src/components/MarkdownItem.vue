<template>
  <div>
    <pre v-html="mdHtml" class="whitespace-normal"></pre>
  </div>
</template>
<script setup lang="ts">
import { ref, defineProps, onMounted } from 'vue';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js/lib/common';
import 'highlight.js/styles/default.min.css';

const props = defineProps(['text']);
const mdHtml = ref('');

function render(ret: string) {
  if (!ret) {
    return;
  }
  ret = ret.replace(/^```/, '').replace(/```$/, '');
  const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
    highlight: function (str, lang): string {
      if (!lang) {
        lang = 'plaintext';
      }
      if (lang && hljs.getLanguage(lang)) {
        try {
          return `<pre class="hljs my-2 p-4 rounded-sm"><code>${
            hljs.highlight(str, { language: lang }).value
          }</code></pre>`;
        } catch (__) {}
      }
      return `<pre class="hljs my-2 p-4 rounded-sm"><code>${md.utils.escapeHtml(str)}</code></pre>`;
    }
  });

  // 重写列表渲染规则
  md.renderer.rules.ordered_list_open = (tokens, idx, options, _, self) => {
    const token = tokens[idx];
    token.attrSet('class', 'list-decimal ml-8');
    return self.renderToken(tokens, idx, options);
  };

  md.renderer.rules.bullet_list_open = (tokens, idx, options, _, self) => {
    const token = tokens[idx];
    token.attrSet('class', 'list-disc ml-8'); // 添加ul的class
    return self.renderToken(tokens, idx, options);
  };

  mdHtml.value = md.render(ret, {});
}
onMounted(() => {
  render(props.text);
});
</script>
