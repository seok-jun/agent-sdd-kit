package example.order;

public interface OrderRepository {
    Order find(long orderId);
}
