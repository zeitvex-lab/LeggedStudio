import { ref } from 'vue';
import type { ChnDetailInfo, PageModel } from './Detail';

export const useModel = (): [PageModel] => {
  const chnDetailInfo = ref<ChnDetailInfo | null>(null);

  return [{ chnDetailInfo }];
};
