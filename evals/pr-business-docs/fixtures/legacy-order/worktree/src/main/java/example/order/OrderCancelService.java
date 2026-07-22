package example.order;

import java.util.List;

public class OrderCancelService {
    private final OrderRepository repository;

    public OrderCancelService(OrderRepository repository) {
        this.repository = repository;
    }

    public void cancel(long orderId, List<Long> itemIds) {
        Order order = repository.find(orderId);
        if (itemIds.isEmpty()) {
            order.cancelAll();
        } else {
            order.cancelPartially(itemIds);
        }
    }
}
