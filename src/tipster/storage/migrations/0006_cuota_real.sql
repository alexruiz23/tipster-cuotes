-- 0006: cuota real a la que se apostó (BACKLOG 45). El feed de The Odds API no es la web .es de la
-- casa: la cuota que el usuario ve y toma puede ser otra. Si se registra, manda sobre la del feed
-- en la liquidación y en el CLV "real"; el CLV del feed (`clv`) se conserva para compararlos.
ALTER TABLE picks ADD COLUMN taken_price REAL CHECK (taken_price > 1);
ALTER TABLE picks ADD COLUMN taken_bookmaker TEXT; -- casa donde se tomó, libre (p. ej. "bwin.es")
ALTER TABLE picks ADD COLUMN taken_at TEXT;
ALTER TABLE picks ADD COLUMN clv_taken REAL; -- taken_price / cuota justa de cierre − 1
