import useDrawer from '@/hooks/useDrawer';
import ConfigOptionsDetail from '@/components/ResourceDrawer.vue';
import { ref } from 'vue';

export const useResourceDrawer = () => {
  const drawer_title = ref<string>('');
  const uuid = ref<number>(0);
  const lang = ref<string>('');

  const [{}, { Drawer: MyDrawer, open: openDrawer }] = useDrawer({
    component: () => {
      return (
        <ConfigOptionsDetail
          title={drawer_title.value}
          uuid={uuid.value}
          defaultLang={lang.value}
        ></ConfigOptionsDetail>
      );
    }
  });

  const openResourceDrawer = (title: string, resource_uuid: number, language?: string): void => {
    drawer_title.value = title;
    uuid.value = resource_uuid;
    lang.value = language || 'yaml';
    openDrawer!();
  };

  return { MyDrawer: MyDrawer!, openResourceDrawer };
};
