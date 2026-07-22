# Quiz Widget for Emacs

This Emacs package converts org-mode quiz entries from квизи.org into interactive Emacs widgets using radio buttons.

## Usage

1. Load the package:
```elisp
(load-file "/path/to/quiz-widget.el")
```

2. To display the quiz with questions from квизи.org:
```elisp
(quiz-widget-display)
```

3. For a quick test:
```elisp
(quiz-widget-simple-test)
```

## Features

- Parses quiz questions from org-mode format
- Converts checkboxes to radio buttons (since only one answer is correct)
- Shows categories as headers
- Interactive answer checking
- Russian language support

## Org-mode Format Expected

The parser expects the format used in квизи.org:

```
*** Category Name [completed/total]
- [ ] Question text?
	 - [X] Correct answer
	 - [ ] Wrong answer
	 - [ ] Another wrong answer
```

## Installation

Add this to your Emacs configuration:

```elisp
(load-file "/home/eugene/org-roam/quiz-widget.el")
```

Then use `M-x quiz-widget-display` to start the quiz.