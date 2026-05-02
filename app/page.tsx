import React from 'react';

export default function Home() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white font-sans p-8">
      <header className="max-w-6xl mx-auto flex justify-between items-center mb-16">
        <h1 className="text-3xl font-black bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent">
          TG-MILLIONAIRE
        </h1>
        <button className="bg-white text-black px-6 py-2 rounded-full font-bold hover:bg-blue-500 hover:text-white transition">
          Войти
        </button>
      </header>

      <main className="max-w-6xl mx-auto text-center">
        <h2 className="text-5xl md:text-7xl font-extrabold mb-6">
          Зарабатывай на <br/> <span className="text-blue-500">качестве.</span>
        </h2>
        <p className="text-gray-400 text-xl mb-12">Автоматическая продажа Telegram аккаунтов</p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
          {/* Карточка товара */}
          <div className="bg-[#111] p-6 rounded-3xl border border-white/5 hover:border-blue-500/50 transition">
            <div className="text-4xl mb-4">🤖</div>
            <h3 className="text-xl font-bold mb-2">Автореги РФ</h3>
            <p className="text-gray-500 mb-4">Чистые номера, формат .session</p>
            <div className="flex justify-between items-center">
              <span className="text-2xl font-bold">49 ₽</span>
              <button className="bg-blue-600 px-4 py-2 rounded-xl text-sm font-bold">Купить</button>
            </div>
          </div>
          {/* Добавь еще карточки здесь */}
        </div>
      </main>
    </div>
  );
                                              }
