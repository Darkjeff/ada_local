from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, 
    QListWidgetItem, QSizePolicy, QWidget, QScrollArea
)
from PySide6.QtCore import Qt, QSize

from qfluentwidgets import (
    LineEdit, ListWidget, CheckBox, PushButton, 
    TransparentToolButton, FluentIcon as FIF,
    CardWidget, HeaderCardWidget, BodyLabel, TitleLabel,
    StrongBodyLabel
)

from gui.components.schedule import ScheduleComponent
from gui.components.timer import TimerComponent
from gui.components.alarm import AlarmComponent
from core.tasks import task_manager


class PlannerTab(QFrame):
    """
    Planner functionality: Focus Tasks, Schedule, and Flow State tools.
    Refined for Aura Theme.
    """
    
    def __init__(self):
        super().__init__()
        self.setObjectName("plannerPanel")
        self.setStyleSheet("background: transparent;")
        
        self.completed_expanded = False
        
        self._setup_ui()
        self._load_tasks()

    def _setup_ui(self):
        planner_layout = QHBoxLayout(self)
        planner_layout.setContentsMargins(30, 30, 30, 30)
        planner_layout.setSpacing(25)
        
        # --- Column 1: Focus Tasks (HeaderCardWidget) ---
        tasks_col = HeaderCardWidget("Focus Tasks")
        tasks_col.setBorderRadius(12)

        t_layout = QVBoxLayout()
        t_layout.setContentsMargins(20, 20, 20, 20)
        t_layout.setSpacing(15)
        
        # New Task Input
        self.task_input = LineEdit()
        self.task_input.setPlaceholderText("Add objective...")
        self.task_input.returnPressed.connect(self._add_task)
        self.task_input.setClearButtonEnabled(True)
        t_layout.addWidget(self.task_input)
        
        # Task Lists (Active)
        self.task_list = ListWidget()
        self.task_list.setStyleSheet("background: transparent; border: none;")
        t_layout.addWidget(self.task_list, 1) # Stretch to fill
        
        # Completed Section
        header_layout = QHBoxLayout()
        self.completed_header_btn = TransparentToolButton(FIF.CHEVRON_RIGHT)
        self.completed_header_btn.clicked.connect(self._toggle_completed_section)
        header_layout.addWidget(self.completed_header_btn)
        
        self.completed_label = BodyLabel("Completed 0")
        self.completed_label.setStyleSheet("color: #8b9bb4;")
        header_layout.addWidget(self.completed_label)
        header_layout.addStretch()
        
        t_layout.addLayout(header_layout)
        
        self.completed_list = ListWidget()
        self.completed_list.setStyleSheet("background: transparent; border: none;")
        self.completed_list.setVisible(False)
        t_layout.addWidget(self.completed_list)
        
        tasks_col.viewLayout.addLayout(t_layout)
        
        planner_layout.addWidget(tasks_col, 1)
        
        # --- Column 2: Schedule (HeaderCardWidget) ---
        schedule_col = HeaderCardWidget("Timeline")
        schedule_col.setBorderRadius(12)
        
        s_layout = QVBoxLayout()
        s_layout.setContentsMargins(0, 0, 0, 0)
        
        self.schedule_component = ScheduleComponent()
        s_layout.addWidget(self.schedule_component)
        
        schedule_col.viewLayout.addLayout(s_layout)
        
        planner_layout.addWidget(schedule_col, 1)
        
        # --- Column 3: Performance Timers ---
        flow_col = QFrame()
        flow_col.setFixedWidth(320)
        flow_col.setStyleSheet("background: transparent; border: none;")
        flow_layout = QVBoxLayout(flow_col)
        flow_layout.setContentsMargins(0, 0, 0, 0)
        flow_layout.setSpacing(25)
        
        # Performance Header
        p_title = StrongBodyLabel("Performance Timers")
        p_title.setStyleSheet("color: #e8eaed; font-size: 14px;")
        flow_layout.addWidget(p_title)
        
        # Timer
        self.timer_component = TimerComponent()
        # Ensure it has a Card-like container if it doesn't already
        flow_layout.addWidget(self.timer_component)
        
        # Alarm
        self.alarm_component = AlarmComponent() 
        flow_layout.addWidget(self.alarm_component)
        
        flow_layout.addStretch()
        
        planner_layout.addWidget(flow_col)

    def _load_tasks(self):
        """Load tasks from persistent storage."""
        tasks = task_manager.get_tasks()
        self.task_list.clear()
        self.completed_list.clear() # Fix duplication bug
        for task in tasks:
            self._create_task_item(task)
            
        self._update_task_counter()
        
    def _add_task(self):
        """Add a new task from the input field."""
        if hasattr(self, 'task_input'):
            task_text = self.task_input.text().strip()
            if task_text:
                self._add_task_from_text(task_text)
                self.task_input.clear()
    
    def _add_task_from_text(self, task_text):
        """Internal helper to add task."""
        # Save to DB
        new_task = task_manager.add_task(task_text)
        if new_task:
            self._create_task_item(new_task)
        self._update_task_counter()
    
    def _on_task_checked(self, state: int, item: QListWidgetItem, source_list: ListWidget):
        """Handle task checkbox state change - move between lists."""
        widget = source_list.itemWidget(item)
        if not widget:
            return
            
        # Get task ID from data
        task_id = item.data(Qt.UserRole)
        
        # Get task text from label
        # We need to find the BodyLabel inside
        label = widget.findChild(BodyLabel)
        if not label:
            # Fallback if using QLabel
            label = widget.findChild(QLabel)
            
        if not label:
            return
        
        task_text = label.text()
        row = source_list.row(item)
        is_completed = (state == Qt.Checked.value)
        
        # Update persistence
        task_manager.toggle_task(task_id, is_completed)
        
        # Start transition
        source_list.takeItem(row)
        
        # Re-create in correct list
        task_data = {"id": task_id, "text": task_text, "completed": is_completed}
        self._create_task_item(task_data)
        
        self._update_task_counter()
    
    def _create_task_item(self, task_data: dict):
        """Create a task item widget and add to appropriate list."""
        completed = task_data.get('completed', False)
        text = task_data.get('text', '')
        task_id = task_data.get('id')
        
        target_list = self.completed_list if completed else self.task_list
        
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 50))
        item.setData(Qt.UserRole, task_id)  # Store ID
        
        task_widget = QWidget()
        task_layout = QHBoxLayout(task_widget)
        task_layout.setContentsMargins(10, 5, 10, 5)
        task_layout.setSpacing(12)
        
        # Checkbox
        checkbox = CheckBox()
        checkbox.setChecked(completed)
        # Fix lambda binding
        checkbox.stateChanged.connect(lambda state, i=item, l=target_list: self._on_task_checked(state, i, l))
        task_layout.addWidget(checkbox)
        
        # Task label
        task_label = BodyLabel(text)
        if completed:
            # Strikethrough style
            task_label.setStyleSheet("color: #8a8a8a; text-decoration: line-through;")
        else:
            task_label.setStyleSheet("color: #e8eaed;") 
            
        task_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        task_layout.addWidget(task_label, 1)
        
        # Delete button
        delete_btn = TransparentToolButton(FIF.DELETE)
        delete_btn.clicked.connect(lambda: self._delete_task(item, target_list))
        task_layout.addWidget(delete_btn)
        
        target_list.addItem(item)
        target_list.setItemWidget(item, task_widget)
    
    def _delete_task(self, item: QListWidgetItem, source_list: ListWidget = None):
        """Delete a task from the list."""
        if source_list is None:
            source_list = self.task_list
            
        task_id = item.data(Qt.UserRole)
        task_manager.delete_task(task_id)
        
        row = source_list.row(item)
        if row >= 0:
            source_list.takeItem(row)
            self._update_task_counter()
    
    def _toggle_completed_section(self):
        """Toggle the completed tasks section visibility."""
        self.completed_expanded = not self.completed_expanded
        self.completed_list.setVisible(self.completed_expanded)
        
        if self.completed_expanded:
            self.completed_header_btn.setIcon(FIF.CHEVRON_DOWN_MED)
        else:
            self.completed_header_btn.setIcon(FIF.CHEVRON_RIGHT)
    
    def _update_task_counter(self):
        """Update the task counter label and completed header."""
        completed_count = self.completed_list.count()
        self.completed_label.setText(f"Completed {completed_count}")
