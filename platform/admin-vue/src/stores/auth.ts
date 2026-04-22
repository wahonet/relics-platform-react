import { defineStore } from 'pinia';

// FastAPI 用 httponly cookie 做登录态，前端拿不到 cookie 值。
// 这里仅用 localStorage 记一个软标记：
//   - 登录成功后设 true，用户名留给 UI 显示
//   - 401 时拦截器清掉，路由守卫看到就跳登录
// 真实鉴权仍以 cookie 为准。
const LS_KEY = 'relics_admin_auth';

interface Persisted {
  authed: boolean;
  username: string;
}

function load(): Persisted {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { authed: false, username: '' };
    return JSON.parse(raw) as Persisted;
  } catch {
    return { authed: false, username: '' };
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => load(),
  actions: {
    setLoggedIn(username: string) {
      this.authed = true;
      this.username = username;
      localStorage.setItem(LS_KEY, JSON.stringify({ authed: true, username }));
    },
    clear() {
      this.authed = false;
      this.username = '';
      localStorage.removeItem(LS_KEY);
    },
  },
});
