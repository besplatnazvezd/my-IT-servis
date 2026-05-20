"use client";
import React, { useState } from 'react';

// В будущем эти данные будут приходить из Supabase
const SERVICES = [
  {
    id: 1,
    title: "Создание Landing Page",
    price: 5000,
    description: "Быстрый и адаптивный сайт на Next.js или HTML/CSS."
  },
  {
    id: 2,
    title: "Настройка Telegram-бота",
    price: 3000,
    description: "Автоматизация ответов и интеграция с Google Таблицами."
  },
  {
    id: 3,
    title: "Дизайн баннера",
    price: 1500,
    description: "Яркий баннер для соцсетей или рекламы."
  }
];

export default function Home() {
  const [loading, setLoading] = useState(false);

  const handleOrder = async (serviceName: string, price: number) => {
    setLoading(true);
    alert(`Вы выбрали: ${serviceName} за ${price}₽. Сейчас здесь будет переход на ЮKassa.`);
    
    // ЛОГИКА ДЛЯ БУДУЩЕГО:
    // 1. Создаем запись в Supabase (статус: "ожидает оплаты")
    // 2. Вызываем API ЮKassa для получения ссылки на оплату
    // 3. Редиректим пользователя на оплату
    
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans">
      {/* Навигация */}
      <nav className="p-6 bg-white shadow-sm flex justify-between items-center">
        <h1 className="text-2xl font-bold text-blue-600">MyFreelance</h1>
        <div className="space-x-4">
          <a href="#" className="hover:text-blue-500">Услуги</a>
          <a href="#" className="hover:text-blue-500">Контакты</a>
        </div>
      </nav>

      {/* Hero секция */}
      <header className="py-20 px-6 text-center">
        <h2 className="text-5xl font-extrabold mb-4">Профессиональные услуги фриланса</h2>
        <p className="text-xl text-gray-600 mb-8">Качественно. Быстро. С гарантией оплаты через ЮKassa.</p>
      </header>

      {/* Список услуг */}
      <main className="max-w-6xl mx-auto px-6 pb-20">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {SERVICES.map((service) => (
            <div key={service.id} className="bg-white p-8 rounded-2xl shadow-lg hover:shadow-xl transition-shadow border border-gray-100 flex flex-col">
              <h3 className="text-xl font-bold mb-2">{service.title}</h3>
              <p className="text-gray-500 mb-6 flex-grow">{service.description}</p>
              <div className="mt-auto">
                <p className="text-2xl font-bold mb-4 text-blue-600">{service.price} ₽</p>
                <button 
                  onClick={() => handleOrder(service.title, service.price)}
                  disabled={loading}
                  className="w-full bg-blue-600 text-white py-3 rounded-xl font-semibold hover:bg-blue-700 transition-colors disabled:bg-gray-400"
                >
                  Заказать
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* Футер */}
      <footer className="bg-white py-10 border-t border-gray-200 text-center text-gray-400">
        <p>© 2024 MyFreelance. Все права защищены.</p>
      </footer>
    </div>
  );
            }
