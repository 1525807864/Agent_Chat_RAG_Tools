//前端登录页面 本地保存 读取 清楚登录token

const TOKEN_KEY = "auth.access_token.v1";
/**
 * 保存登录成功后的jwt token到本地
 */
export function saveToken(token:string):void {
    //trim防止复制时带空格
    const t = (token || "").trim();
    if (!t) {
        clearToken();
        return;
    }
    //写入浏览器到本地存储 
    localStorage.setItem(TOKEN_KEY,t);
}
/**
 * 读取当前JWT，没有则返回空串
 */
export function loadToken(): string {
    try{
        return localStorage.getItem(TOKEN_KEY) || "";
    }catch{
        //隐私模式等异常 当作没有登录
        return ""
    }
}
//清除本地登录token
export function clearToken(): void {
    try {
        localStorage.removeItem(TOKEN_KEY);
    }catch{
        //隐私模式等异常 忽略
    }
}
/**
 * 拼authorization头：无token时返回空对象，有则Bearer开头
 */
export function authHeaders(): Record<string,string> {
    const token = loadToken();
    //没有token 不附加头 (auth_ENABLED=false时仍可以访问)
    if(!token) return {};
    //有token 附加Authorization头
    return {
        Authorization: `Bearer ${token}`,
    }
}

