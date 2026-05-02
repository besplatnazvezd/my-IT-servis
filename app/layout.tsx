import './globals.css'

export const metadata = {
  title: 'TG Shop - Перепродажа аккаунтов',
  description: 'Лучший сервис по продаже аккаунтов Телеграм',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  )
}
