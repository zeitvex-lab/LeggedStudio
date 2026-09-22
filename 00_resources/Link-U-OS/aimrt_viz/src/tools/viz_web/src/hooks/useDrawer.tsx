import { ElDrawer } from 'element-plus';
import { ref, unref, type Ref } from 'vue';
interface DialogParams<T> {
  title?: string | Ref<string>;
  component: any;
  width?: number | string;
  onConfirm?: (formData: T) => void;
  onCancel?: () => void;
}
export default function useDrawer<T>(params: DialogParams<T>) {
  const visible = ref(false);
  const componentRef = ref();
  const defaultWidth = '50%';
  const open = () => {
    visible.value = true;
  };
  const close = () => {
    visible.value = false;
  };
  const cancel = () => {
    close();
    params?.onCancel?.();
  };
  const confirm = (ret: T) => {
    close();
    params?.onConfirm?.(ret);
  };
  return [
    {},
    {
      open,
      close,
      Drawer: () => (
        <ElDrawer
          modelValue={visible.value}
          onUpdate:modelValue={(v: boolean) => (visible.value = v)}
          title={unref(params.title)}
          closeOnClickModal={true}
          size={params.width ?? defaultWidth}
        >
          <div>
            <params.component
              key={visible.value}
              ref={componentRef}
              onCancel={cancel}
              onConfirm={confirm}
            ></params.component>
          </div>
        </ElDrawer>
      )
    }
  ];
}
