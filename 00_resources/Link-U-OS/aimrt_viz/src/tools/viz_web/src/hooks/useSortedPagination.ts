import { ref, computed, type Ref, type ComputedRef } from 'vue';

// 类型定义
type SortOrder = 'ascending' | 'descending' | null;

interface SortChangeParams {
  column: any;
  prop: string | null;
  order: SortOrder;
}

interface SortedPaginationOptions {
  defaultSortField?: string;
  defaultSortOrder?: SortOrder;
  defaultPageSize?: number;
}

interface SortedPaginationReturn<T> {
  currentPage: Ref<number>;
  pageSize: Ref<number>;
  sortField: Ref<string>;
  sortOrder: Ref<SortOrder>;
  sortedData: ComputedRef<T[]>;
  currentPageData: ComputedRef<T[]>;
  handleSortChange: (params: SortChangeParams) => void;
  handleSizeChange: (val: number) => void;
  handleCurrentChange: (val: number) => void;
  resetToFirstPage: () => void;
}

// 提取公共工具函数
const getNestedValue = (obj: any, path: string): any => {
  if (!path) return obj;
  return path.split('.').reduce((current, key) => current?.[key], obj);
};

// 提取核心比较逻辑
const compareValues = (aVal: any, bVal: any): number => {
  // 处理 null/undefined
  if (aVal == null && bVal == null) return 0;
  if (aVal == null) return 1;
  if (bVal == null) return -1;

  // 数字排序
  if (typeof aVal === 'number' && typeof bVal === 'number') {
    return aVal - bVal;
  }

  // 字符串排序（支持中文）
  return String(aVal).localeCompare(String(bVal), 'zh-CN', {
    numeric: true,
    sensitivity: 'base'
  });
};

// 重构后的 sortArray 函数
export const sortArray = <T>(data: T[], field: string, order: SortOrder = 'ascending'): T[] => {
  if (!field || !order || !data.length) {
    return [...data];
  }

  return [...data].sort((a: T, b: T) => {
    const aVal = getNestedValue(a, field);
    const bVal = getNestedValue(b, field);
    const comparison = compareValues(aVal, bVal);

    return order === 'ascending' ? comparison : -comparison;
  });
};

export const useSortedPagination = <T>(
  filteredData: Ref<T[]>,
  options: SortedPaginationOptions = {}
): SortedPaginationReturn<T> => {
  const { defaultSortField = '', defaultSortOrder = 'ascending', defaultPageSize = 10 } = options;

  // 响应式状态
  const currentPage = ref<number>(1);
  const pageSize = ref<number>(defaultPageSize);
  const sortField = ref<string>(defaultSortField);
  const sortOrder = ref<SortOrder>(defaultSortOrder);

  // 计算属性：排序后的数据 - 直接使用 sortArray 函数
  const sortedData = computed<T[]>(() => {
    return sortArray(filteredData.value, sortField.value, sortOrder.value);
  });

  // 计算属性：当前页显示的数据
  const currentPageData = computed<T[]>(() => {
    const start = (currentPage.value - 1) * pageSize.value;
    const end = start + pageSize.value;
    return sortedData.value.slice(start, end);
  });

  // 排序处理
  const handleSortChange = ({ prop, order }: SortChangeParams): void => {
    if (order === null && defaultSortField) {
      sortField.value = defaultSortField;
      sortOrder.value = defaultSortOrder;
    } else {
      sortField.value = prop || '';
      sortOrder.value = order;
    }
    resetToFirstPage();
  };

  // 分页处理
  const handleSizeChange = (val: number): void => {
    pageSize.value = val;
    resetToFirstPage();
  };

  const handleCurrentChange = (val: number): void => {
    currentPage.value = val;
  };

  // 重置到第一页
  const resetToFirstPage = (): void => {
    currentPage.value = 1;
  };

  return {
    currentPage,
    pageSize,
    sortField,
    sortOrder,
    sortedData,
    currentPageData,
    handleSortChange,
    handleSizeChange,
    handleCurrentChange,
    resetToFirstPage
  };
};
