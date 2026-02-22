let rawBaseUrl = process.env.REACT_APP_API_BASE_URL || 'https://kv08u5rxg2.execute-api.us-east-1.amazonaws.com';
if (!rawBaseUrl.endsWith('/backend')) {
    rawBaseUrl = `${rawBaseUrl.replace(/\/+$/, '')}/backend`;
}
export const API_BASE_URL = rawBaseUrl;


