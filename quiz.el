(require 'org)
(require 'subr-x)
(require 'cl-lib)
(ignore-errors (require 'org-ql))

(defun quiz-org-ql-count-by-category ()
  "Return an alist (CATEGORY . COUNT) of questions in current buffer.
Questions are identified by having a CATEGORY property.
Uses org-ql if available; falls back to org-element-map."
  (interactive)
  (unless (derived-mode-p 'org-mode)
    (user-error "Run this command in an Org buffer"))
  (let ((counts (make-hash-table :test 'equal)))
    ;; Try org-ql first if available
    (if (featurep 'org-ql)
        (let ((items (org-ql-select (current-buffer)
                       '(property "CATEGORY")
                       :action (lambda () (org-entry-get nil "CATEGORY"))
)))
                       ;; :flatten t)))
          (dolist (cat items)
            (puthash cat (1+ (gethash cat counts 0)) counts)))
      ;; Fallback to org-element-map
      (org-element-map (org-element-parse-buffer) 'headline
        (lambda (h)
          (let ((category (org-element-property :CATEGORY h)))
            (when category
              (puthash category (1+ (gethash category counts 0)) counts))))))
    (let (out)
      (maphash (lambda (k v) (push (cons k v) out)) counts)
      (setq out (sort out (lambda (a b) (string< (car a) (car b)))))
      (when (called-interactively-p 'interactive)
        (message "%s" (mapconcat (lambda (kv) (format "%s: %d" (car kv) (cdr kv))) out ", ")))
      out)))

(defun quiz--slugify (s)
  "Create a short slug from S suitable for an ID.
Lowercases, trims, replaces runs of non-alphanum with hyphens,
and truncates to ~40 chars (preserving multibyte)."
  (let ((raw (downcase (string-trim s)))
        ;; replace whitespace/newlines with single space first
        (one (replace-regexp-in-string "[[:space:]\n\r\t]+" " " raw))
        (slug (replace-regexp-in-string "[^[:alnum:]]+" "-" one)))
    (let ((trimmed (replace-regexp-in-string "^-+\\|-+$" "" slug)))
      (if (> (length trimmed) 40) (substring trimmed 0 40) trimmed))))

(defun quiz--make-human-id (question)
  "Return a human-readable ID for QUESTION: slug + '-' + 8-char sha1 suffix."
  (let ((sha (substring (sha1 question) 0 8)))
    (concat (quiz--slugify question) "-" sha)))

(defun quiz--extract-items-in-plain-list (plist)
  "Return list of item plists from plain-list element PLIST.
Each item plist: (:begin :end :question :answers :checked-index)
answers is a vector of 4 strings; checked-index is 0-based index of correct answer."
  (let (out)
    (dolist (item (org-element-contents plist))
      (when (eq (org-element-type item) 'item)
        (let ((ib (org-element-property :begin item))
               (ie (org-element-property :end item))
               (first-line
                (save-excursion
                  (goto-char ib)
                  (let ((line (buffer-substring-no-properties ib (line-end-position))))
                    (string-trim
                     (replace-regexp-in-string "^\\s-[-+]\\s-\\(\\[.\\]\\s-\\)?" "" line))))))
               answers checks)
          ;; Collect answer list items inside item (children plain-list or list items).
          ;; We'll scan region between ib and ie for list items with checkbox marker.
          (save-excursion
            (goto-char ib)
            (while (re-search-forward "^\\s-[-+]\\s-\\(\\[.\\]\\)\\s-\\(.*\\)$" ie t)
              (let ((chk (match-string 1))
                    (txt (string-trim (match-string 2))))
                (push txt answers)
                (push (and chk (not (string= chk "[ ]")) ) checks))))
          (when answers
            (setq answers (nreverse answers))
            (setq checks (nreverse checks))
            ;; store
            (push (list :begin ib :end ie :question first-line
                        :answers answers :checks checks)
                  out))))
    (nreverse out)))

(provide 'quiz)
