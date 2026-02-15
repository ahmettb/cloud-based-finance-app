const rawBaseUrl = process.env.REACT_APP_API_BASE_URL || 'https://omph0szx5b.execute-api.us-east-1.amazonaws.com/prod';
export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, '');
