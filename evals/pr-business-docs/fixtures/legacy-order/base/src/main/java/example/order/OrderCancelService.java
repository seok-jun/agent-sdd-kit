package example.order;

public class OrderCancelService {
    private final OrderRepository repository;

    public OrderCancelService(OrderRepository repository) {
        this.repository = repository;
    }

    public void cancel(long orderId) {
        Order order = repository.find(orderId);
        order.cancelAll();
    }
}
