export const CATEGORY_OPTIONS = [
    { id: 1, name: 'Market', icon: 'shopping_cart' },
    { id: 2, name: 'Restoran', icon: 'restaurant' },
    { id: 3, name: 'Kafe', icon: 'coffee' },
    { id: 4, name: 'Online Alışveriş', icon: 'shopping_bag' },
    { id: 5, name: 'Fatura', icon: 'receipt_long' },
    { id: 6, name: 'Konaklama', icon: 'hotel' },
    { id: 7, name: 'Ulaşım', icon: 'commute' },
    { id: 9, name: 'Abonelik', icon: 'subscriptions' },
    { id: 10, name: 'Eğitim', icon: 'school' },
    { id: 8, name: 'Diğer', icon: 'category' }
];

export const CATEGORY_NAME_TO_ID = CATEGORY_OPTIONS.reduce((acc, item) => {
    acc[item.name.toLowerCase()] = item.id;
    return acc;
}, {});

export const CATEGORY_ID_TO_NAME = CATEGORY_OPTIONS.reduce((acc, item) => {
    acc[item.id] = item.name;
    return acc;
}, {});

export const VARIABLE_CATEGORIES = CATEGORY_OPTIONS.map((c) => c.name);

export const FIXED_GROUP_CATEGORIES = ['Kira', 'Fatura', 'Abonelik', 'Kredi', 'Eğitim', 'Diğer'];

export const normalizeCategoryName = (value) => {
    if (!value) return '';
    return String(value)
        .trim()
        .toLowerCase()
        .replace(/ı/g, 'i')
        .replace(/ş/g, 's')
        .replace(/ç/g, 'c')
        .replace(/ğ/g, 'g')
        .replace(/ü/g, 'u')
        .replace(/ö/g, 'o');
};

export const resolveCategoryId = (value) => {
    if (value === null || value === undefined) return 8;
    if (typeof value === 'number') return CATEGORY_ID_TO_NAME[value] ? value : 8;
    const normalized = normalizeCategoryName(value);
    const directMatch = CATEGORY_NAME_TO_ID[normalized];
    if (directMatch) return directMatch;

    const aliases = {
        gida: 1,
        market: 1,
        restoran: 2,
        restaurant: 2,
        kafe: 3,
        cafe: 3,
        eglence: 4,
        online: 4,
        fatura: 5,
        barinma: 6,
        konaklama: 6,
        ulasim: 7,
        abonelik: 9,
        egitim: 10,
        saglik: 8,
        giyim: 8,
        teknoloji: 4,
        diger: 8
    };
    return aliases[normalized] || 8;
};
