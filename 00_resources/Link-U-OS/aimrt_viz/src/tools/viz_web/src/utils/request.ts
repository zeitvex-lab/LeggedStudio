import axios from 'axios';
import { ElMessage } from 'element-plus';
import _isNil from 'lodash-es/isNil';

const request = axios.create({
  timeout: 180000,
  headers: {}
});
request.interceptors.response.use((resp) => {
  const { data: httpData } = resp;
  try {
    if (typeof httpData == 'string') {
      return resp;
    } else if (!_isNil(httpData.code)) {
      let { code, message } = httpData as {
        code: number;
        message: string;
        data: any;
      };
      if (code !== 0) {
        console.error(message);
        ElMessage({
          message: `${message}'}`,
          type: 'error',
          duration: 4000,
          offset: 20,
          customClass: 'header-message'
        });
        return Promise.reject(message);
      }
    }
  } catch (error) {}
  return resp;
});

export async function getJSONL(url: string): Promise<any[]> {
  const response = await request.get(url);
  const text = response.data as string;
  if (!text) {
    return [];
  }
  return text
    .split('\n')
    .filter((line: string) => line.trim())
    .map((line: string) => JSON.parse(line));
}

export { request };
