from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
import json

class ProductCreate(BaseModel):
    original_url: HttpUrl
    affiliate_url: HttpUrl
    marketplace: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=5000)

class ProductUpdate(BaseModel):
    affiliate_url: HttpUrl | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    marketplace: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    price: float | None = Field(default=None, ge=0)
    original_price: float | None = Field(default=None, ge=0)
    price_note: str | None = Field(default=None, max_length=60)
    store: str | None = Field(default=None, max_length=160)
    availability: str | None = Field(default=None, max_length=80)

class BrowserCapture(BaseModel):
    """Dados lidos pela extensão na página do produto aberta no navegador do usuário."""
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=5000)
    image_url: str = Field(default="", max_length=2048)
    price: float | None = Field(default=None, ge=0)
    original_price: float | None = Field(default=None, ge=0)
    price_note: str = Field(default="", max_length=60)
    store: str = Field(default="", max_length=160)
    page_url: str = Field(default="", max_length=2048)
    # Link de afiliado gerado pela extensão (botão Compartilhar do Mercado Livre).
    affiliate_link: str = Field(default="", max_length=2048)
    # Preço no cartão quando o preço em destaque depende de Pix/Mercado Pago, e as condições lidas.
    regular_price: float | None = Field(default=None, ge=0)
    price_conditions: str = Field(default="", max_length=300)
    # False quando a loja diz que o produto acabou ou o anúncio está pausado.
    available: bool = True

class BrowserProductCreate(BrowserCapture):
    """Cadastro feito pela extensão a partir da página do produto aberta no navegador."""
    original_url: HttpUrl
    affiliate_url: HttpUrl | None = None
    marketplace: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=100)
    # "Cadastrar e pôr na fila": cria a publicação já aprovada para este grupo.
    enqueue: bool = False
    group_name: str = Field(default="", max_length=160)

class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_url: str
    affiliate_url: str
    marketplace: str
    category: str
    notes: str
    title: str
    description: str
    image_url: str
    price: float | None
    original_price: float | None
    price_note: str = ""
    data_source: str = ""
    captured_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, value):
        if isinstance(value, str):
            try:
                value = json.loads(value or "[]")
            except ValueError:
                value = []
        return [t for t in value or [] if isinstance(t, str)]
    store: str
    availability: str
    status: str
    created_at: datetime


class BulkProducts(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)

class BulkProductUpdate(BulkProducts):
    """Alteração em massa: categoria (vazio limpa) e tags a adicionar ou remover."""
    category: str | None = Field(default=None, max_length=100)
    add_tags: list[str] = Field(default_factory=list, max_length=30)
    remove_tags: list[str] = Field(default_factory=list, max_length=30)
