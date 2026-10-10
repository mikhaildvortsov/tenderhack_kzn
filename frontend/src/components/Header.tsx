export default function Header() {
  return (
    <header className="portal-h">
      <div className="portal-h-in">
        <a className="logo" href="#top" aria-label="Портал поставщиков">
          <span className="logo-sq" aria-hidden="true"><span /></span>
          <span className="logo-t">ПОРТАЛ<br />ПОСТАВЩИКОВ</span>
        </a>
        <nav aria-label="Основное меню" className="menu">
          <span className="menu-i active">Каталог</span>
          <span className="menu-i" aria-disabled="true">Закупки</span>
          <span className="menu-i" aria-disabled="true">Поставщикам</span>
          <span className="menu-i" aria-disabled="true">Заказчикам</span>
        </nav>
        <span className="user" aria-hidden="true">Личный кабинет</span>
      </div>
    </header>
  );
}
