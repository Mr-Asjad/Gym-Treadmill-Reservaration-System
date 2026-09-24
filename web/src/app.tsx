import { useEffect, useState } from "react";
import { Book } from "./routes/book";
import { Floor } from "./routes/floor";

function usePath(): [string, (to: string) => void] {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const navigate = (to: string) => {
    if (to !== window.location.pathname) {
      window.history.pushState(null, "", to);
      setPath(to);
    }
  };
  return [path, navigate];
}

export function App() {
  const [path, navigate] = usePath();
  const route = path.startsWith("/floor") ? "floor" : "book";

  const link = (to: string, label: string, key: string) => (
    <a
      href={to}
      aria-current={route === key ? "page" : undefined}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
    >
      {label}
    </a>
  );

  return (
    <div className="shell">
      <header className="topbar">
        <div className="wordmark">
          <span className="bars" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          Reserved&nbsp;Row
        </div>
        <nav className="nav">
          {link("/", "Book", "book")}
          {link("/floor", "Floor", "floor")}
        </nav>
      </header>

      {route === "floor" ? <Floor /> : <Book />}
    </div>
  );
}
