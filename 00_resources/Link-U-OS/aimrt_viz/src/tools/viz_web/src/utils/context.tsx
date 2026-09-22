import { defineComponent, inject, provide, ref, onUnmounted, type Ref, watchEffect } from 'vue';
import _uniqueId from 'lodash-es/uniqueId';
import _isNil from 'lodash-es/isNil';
class ContextCreator<T> {
  _provideLKey: string;
  ctx: Ref<T> | undefined = undefined;
  constructor(initValue?: T) {
    this._provideLKey = _uniqueId('ContextProviderKey');
    let value = ref<T>(initValue as T);
    this.ctx = value as Ref<T>;
  }
  Provider = defineComponent<{ value?: T }>({
    props: {
      value: {
        type: Object,
        required: false
      }
    },
    setup: (props, { slots }) => {
      watchEffect(() => {
        if (!_isNil(props.value)) {
          this.ctx!.value = props.value as T;
        } else if (!this.ctx?.value) {
          // 如果 prop传值空进行初始化但是constructor却有值，那就不值空，否则可以置为空
          this.ctx!.value = props.value as T;
        }
      });
      provide(this._provideLKey, this.ctx);

      onUnmounted(() => {
        this.ctx!.value = undefined as T;
      });
      return () => slots?.default?.();
    }
  });
}
export function useContext<T>(contextCreator: ContextCreator<T>): Ref<T> | undefined {
  return inject<Ref<T>>(contextCreator._provideLKey);
}
export function createContext<T>(initValue?: T) {
  return new ContextCreator<T>(initValue);
}
